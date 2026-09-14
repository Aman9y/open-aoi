"""Run the inspection engine over a whole dataset — one command, full artefacts.

    py scripts/run_dataset.py --dataset synthetic_v1

For every image it writes, under ``outputs/datasets/<dataset>/<name>/``:
    original.png  cropped.png  aligned.png  annotated.png  montage.png  result.json
plus a dataset-level ``summary.csv``, ``summary.md`` and a ``contact_sheet.png``
(all montages stacked). No fake predictions — the engine runs for real on each image.
"""

from __future__ import annotations

import sys as _sys
try:
    _sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import argparse
import csv
import json
import shutil
from pathlib import Path

import _bootstrap  # noqa: F401
import cv2
import numpy as np

from app.config import get_settings
from app.inspection.pipeline import run_inspection
from app.sources import FileSource
from app.storage.reference_repository import ReferenceRepository


def _load_manifest(ds_dir: Path) -> tuple[list[dict], str | None]:
    mf = ds_dir / "manifest.json"
    if mf.is_file():
        data = json.loads(mf.read_text("utf-8"))
        return data["images"], data.get("reference_id")
    # Fallback: infer from filename prefix.
    prefix = {"good": "GOOD", "defect": "DEFECTIVE", "review": "REVIEW"}
    return [
        {"file": f"images/{p.name}" if (ds_dir / "images").is_dir() else p.name,
         "label": prefix.get(p.stem.split("_", 1)[0], ""), "expected_defects": [], "note": ""}
        for p in sorted((ds_dir / "images" if (ds_dir / "images").is_dir() else ds_dir).glob("*"))
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

    entries, manifest_ref = _load_manifest(ds_dir)
    profile = ReferenceRepository(cfg).load_profile(args.reference or manifest_ref)
    out_root = cfg.outputs_dir / "datasets" / args.dataset
    if out_root.exists():
        shutil.rmtree(out_root)
    out_root.mkdir(parents=True)

    rows: list[dict] = []
    montages: list[np.ndarray] = []

    for entry in entries:
        name = Path(entry["file"]).stem
        img_path = ds_dir / entry["file"]
        result = run_inspection(FileSource(img_path).read(), profile, cfg)

        dest = out_root / name
        dest.mkdir(parents=True, exist_ok=True)
        src = cfg.outputs_dir / result.inspection_id
        for f in ("original.png", "cropped.png", "aligned.png", "annotated.png", "montage.png", "result.json"):
            if (src / f).is_file():
                shutil.copy(src / f, dest / f)

        expected = entry.get("label", "")
        got = result.status.value
        exp_def = set(entry.get("expected_defects", []))
        got_def = {f"{d.component}:{d.type.value}" for d in result.defects}
        rows.append({
            "name": name,
            "expected": expected,
            "predicted": got,
            "match": "ok" if expected == got else "MISMATCH",
            "reason": result.reason.value,
            "detect": f"{result.detection.method}/{result.detection.coverage}",
            "align": "ok" if result.alignment.success else "fail",
            "align_err_px": result.alignment.alignment_error_px,
            "board_ssim": result.board_similarity,
            "conf": round(result.overall_confidence, 3),
            "time_ms": result.inspection_time_ms,
            "expected_defects": ";".join(sorted(exp_def)) or "-",
            "found_defects": ";".join(sorted(got_def)) or "-",
            "defect_match": "ok" if exp_def == got_def else ("n/a" if not exp_def and expected != "DEFECTIVE" else "DIFF"),
        })
        if (dest / "montage.png").is_file():
            montages.append(cv2.imread(str(dest / "montage.png")))

    # ---- summary.csv ----
    with (out_root / "summary.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    # ---- summary.md ----
    n = len(rows)
    status_ok = sum(r["match"] == "ok" for r in rows)
    false_accept = [r for r in rows if r["expected"] == "DEFECTIVE" and r["predicted"] == "GOOD"]
    md = [
        f"# Dataset run — {args.dataset}\n",
        f"- reference: `{profile.id}`  ·  images: {n}",
        f"- status correct: {status_ok}/{n}",
        f"- **false accepts (DEFECTIVE read as GOOD): {len(false_accept)}**",
        f"- board detected: {sum(1 for r in rows if not r['detect'].startswith('none'))}/{n}",
        f"- alignment ok: {sum(1 for r in rows if r['align'] == 'ok')}/{n}",
        f"- avg time: {round(sum(r['time_ms'] for r in rows) / n, 1)} ms",
        "",
        "| image | expected | predicted | reason | detect | align | SSIM | found defects |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        mark = "" if r["match"] == "ok" else " ⚠"
        md.append(f"| {r['name']} | {r['expected']} | {r['predicted']}{mark} | {r['reason']} "
                  f"| {r['detect']} | {r['align']} | {r['board_ssim']} | {r['found_defects']} |")
    (out_root / "summary.md").write_text("\n".join(md), "utf-8")

    # ---- contact_sheet.png ----
    if montages:
        w = max(m.shape[1] for m in montages)
        padded = [cv2.copyMakeBorder(m, 0, 12, 0, w - m.shape[1], cv2.BORDER_CONSTANT, value=(20, 20, 20))
                  for m in montages]
        cv2.imwrite(str(out_root / "contact_sheet.png"), cv2.vconcat(padded))

    print("\n".join(md[:8]))
    print(f"\nartefacts: {out_root}")
    print(f"  summary.md · summary.csv · contact_sheet.png · <name>/montage.png")
    if false_accept:
        print(f"\n!! FALSE ACCEPT(S): {[r['name'] for r in false_accept]}")


if __name__ == "__main__":
    main()
