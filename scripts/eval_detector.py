"""Evaluate a trained YOLO detector on its held-out val split (mAP, P, R).

Requires:  pip install -r backend/requirements-ml.txt

    py scripts/eval_detector.py --data data/datasets/pcb_said_yolo/data.yaml \
                                --weights models/component_detector.pt

Writes outputs/eval/detector/<name>/metrics.json. This is the ONLY place a
component-detector accuracy number should come from — do not quote mAP that has
not been produced here on data the model did not train on.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import _bootstrap  # noqa: F401

from app.config import get_settings


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", required=True, type=Path)
    ap.add_argument("--weights", required=True, type=Path)
    ap.add_argument("--imgsz", type=int, default=896)
    ap.add_argument("--split", default="val", choices=["val", "test"])
    args = ap.parse_args()

    if not args.weights.is_file():
        raise SystemExit(f"weights not found: {args.weights}")
    try:
        from ultralytics import YOLO
    except ImportError:
        raise SystemExit("ultralytics not installed.  pip install -r backend/requirements-ml.txt")

    model = YOLO(str(args.weights))
    m = model.val(data=str(args.data), imgsz=args.imgsz, split=args.split, verbose=True)

    out = get_settings().outputs_dir / "eval" / "detector" / args.weights.stem
    out.mkdir(parents=True, exist_ok=True)
    metrics = {
        "weights": str(args.weights),
        "data": str(args.data),
        "split": args.split,
        "mAP50": round(float(m.box.map50), 4),
        "mAP50_95": round(float(m.box.map), 4),
        "precision": round(float(m.box.mp), 4),
        "recall": round(float(m.box.mr), 4),
        "per_class_mAP50": {
            model.names[i]: round(float(v), 4) for i, v in zip(m.box.ap_class_index, m.box.ap50)
        },
    }
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2), "utf-8")
    print(json.dumps(metrics, indent=2))
    print(f"\nwritten: {out / 'metrics.json'}")


if __name__ == "__main__":
    main()
