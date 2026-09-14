"""Compute classification + localization metrics for a labelled dataset.

    py scripts/evaluate.py --dataset synthetic_v1

Reads ``data/datasets/<name>/manifest.json`` (falls back to filename-prefix
labels: good_* / defect_* / review_*). Runs the engine for real on every image
and reports accuracy / precision / recall / F1 / FP rate / FN rate, defect
localization, average time, and — highlighted separately — **FALSE ACCEPTS**
(a DEFECTIVE board classified GOOD), the critical error class.

Writes ``outputs/eval/<dataset>/report.{json,md}``.
For per-image images (original/cropped/aligned/annotated/montage) use
``scripts/run_dataset.py`` instead.
"""

from __future__ import annotations

import sys as _sys
try:
    _sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import argparse
import datetime as dt
import json
from pathlib import Path

import _bootstrap  # noqa: F401

from app.config import get_settings
from app.inspection.pipeline import run_inspection
from app.sources import FileSource
from app.storage.reference_repository import ReferenceRepository

PREFIX = {"good": "GOOD", "defect": "DEFECTIVE", "review": "REVIEW"}


def load_entries(ds_dir: Path) -> tuple[list[dict], str | None]:
    mf = ds_dir / "manifest.json"
    if mf.is_file():
        data = json.loads(mf.read_text("utf-8"))
        return data["images"], data.get("reference_id")
    img_dir = ds_dir / "images" if (ds_dir / "images").is_dir() else ds_dir
    return [
        {
            "file": str(p.relative_to(ds_dir)),
            "label": PREFIX.get(p.stem.split("_", 1)[0], ""),
            "expected_defects": [],
        }
        for p in sorted(img_dir.glob("*"))
        if p.suffix.lower() in {".png", ".jpg", ".jpeg"}
    ], None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", default="synthetic_v1")
    ap.add_argument("--reference", default=None)
    args = ap.parse_args()

    cfg = get_settings()
    ds_dir = cfg.data_dir / "datasets" / args.dataset
    if not ds_dir.is_dir():
        raise SystemExit(f"dataset not found: {ds_dir}\nrun: py scripts/make_synthetic_pcb.py")

    entries, manifest_ref = load_entries(ds_dir)
    profile = ReferenceRepository(cfg).load_profile(args.reference or manifest_ref)

    rows: list[dict] = []
    loc_hits = loc_total = 0
    for e in entries:
        label = e.get("label", "")
        if label not in {"GOOD", "DEFECTIVE", "REVIEW"}:
            continue
        res = run_inspection(FileSource(ds_dir / e["file"]).read(), profile, cfg)
        exp_def = set(e.get("expected_defects", []))
        got_def = {f"{d.component}:{d.type.value}" for d in res.defects}
        got_comp = {d.component for d in res.defects}
        if exp_def:
            loc_total += len(exp_def)
            loc_hits += sum(1 for d in exp_def if d.split(":")[0] in got_comp)
        rows.append(
            {
                "file": Path(e["file"]).name,
                "expected": label,
                "predicted": res.status.value,
                "reason": res.reason.value,
                "time_ms": res.inspection_time_ms,
                "expected_defects": sorted(exp_def),
                "found_defects": sorted(got_def),
            }
        )

    n = len(rows)
    correct = sum(r["expected"] == r["predicted"] for r in rows)
    tp = sum(r["expected"] == "DEFECTIVE" and r["predicted"] == "DEFECTIVE" for r in rows)
    fp = sum(r["expected"] != "DEFECTIVE" and r["predicted"] == "DEFECTIVE" for r in rows)
    fn = sum(r["expected"] == "DEFECTIVE" and r["predicted"] != "DEFECTIVE" for r in rows)
    tn = sum(r["expected"] != "DEFECTIVE" and r["predicted"] != "DEFECTIVE" for r in rows)
    false_accepts = [r for r in rows if r["expected"] == "DEFECTIVE" and r["predicted"] == "GOOD"]

    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0

    summary = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "dataset": args.dataset,
        "reference_id": profile.id,
        "n": n,
        "accuracy": round(correct / n, 4) if n else 0.0,
        "precision_defective": round(precision, 4),
        "recall_defective": round(recall, 4),
        "f1_defective": round(f1, 4),
        "false_positive_rate": round(fp / (fp + tn), 4) if fp + tn else 0.0,
        "false_negative_rate": round(fn / (fn + tp), 4) if fn + tp else 0.0,
        "FALSE_ACCEPTS": len(false_accepts),
        "false_accept_files": [r["file"] for r in false_accepts],
        "defect_localization": round(loc_hits / loc_total, 4) if loc_total else None,
        "avg_time_ms": round(sum(r["time_ms"] for r in rows) / n, 1) if n else 0.0,
        "confusion": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
        "rows": rows,
    }

    out = cfg.outputs_dir / "eval" / args.dataset
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(json.dumps(summary, indent=2), "utf-8")

    md = [
        f"# Evaluation — {args.dataset}\n",
        f"- generated: {summary['generated_at']}",
        f"- reference: `{profile.id}`  ·  images: {n}",
        "",
        "| metric | value |",
        "|---|---|",
        f"| accuracy | {summary['accuracy']:.3f} |",
        f"| precision (DEFECTIVE) | {summary['precision_defective']:.3f} |",
        f"| recall (DEFECTIVE) | {summary['recall_defective']:.3f} |",
        f"| F1 (DEFECTIVE) | {summary['f1_defective']:.3f} |",
        f"| false positive rate | {summary['false_positive_rate']:.3f} |",
        f"| false negative rate | {summary['false_negative_rate']:.3f} |",
        f"| defect localization | "
        f"{'n/a' if summary['defect_localization'] is None else f'{summary['defect_localization']:.3f}'} |",
        f"| **FALSE ACCEPTS (defective read as GOOD)** | **{summary['FALSE_ACCEPTS']}** |",
        f"| avg inspection time | {summary['avg_time_ms']:.0f} ms |",
        "",
        "| file | expected | predicted | reason | found defects |",
        "|---|---|---|---|---|",
    ]
    for r in rows:
        mark = "" if r["expected"] == r["predicted"] else " ⚠"
        md.append(
            f"| {r['file']} | {r['expected']} | {r['predicted']}{mark} | {r['reason']} | "
            f"{', '.join(r['found_defects']) or '—'} |"
        )
    (out / "report.md").write_text("\n".join(md), "utf-8")

    print("\n".join(md))
    print(f"\nreport: {out / 'report.md'}")
    if false_accepts:
        print(f"\n!! {len(false_accepts)} FALSE ACCEPT(S): {[r['file'] for r in false_accepts]}")


if __name__ == "__main__":
    main()
