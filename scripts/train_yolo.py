"""Train a YOLO component detector. Runs OUTSIDE the web server.

Requires the optional ML deps:  pip install -r backend/requirements-ml.txt

    py scripts/train_yolo.py --data data/datasets/pcb_said_yolo/data.yaml
    py scripts/train_yolo.py --data <data.yaml> --model yolo11s.pt --epochs 100 --imgsz 960

On completion the best weights are copied to ``models/component_detector.pt``.
Point the app at them with:

    AOI_YOLO_MODEL_PATH=models/component_detector.pt

Nothing about accuracy is claimed until you run scripts/eval_detector.py on a
held-out split.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import _bootstrap  # noqa: F401

from app.config import REPO_ROOT


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", required=True, type=Path, help="path to data.yaml")
    ap.add_argument("--model", default="yolo11n.pt", help="base weights (auto-downloaded)")
    ap.add_argument("--epochs", type=int, default=80)
    ap.add_argument("--imgsz", type=int, default=896)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--device", default=None, help="'0' for GPU, 'cpu', or leave for auto")
    ap.add_argument("--name", default="component_detector")
    args = ap.parse_args()

    if not args.data.is_file():
        raise SystemExit(f"data.yaml not found: {args.data}\nrun scripts/prepare_dataset.py first")

    try:
        from ultralytics import YOLO
    except ImportError:
        raise SystemExit(
            "ultralytics is not installed.\n  pip install -r backend/requirements-ml.txt"
        )

    model = YOLO(args.model)
    results = model.train(
        data=str(args.data),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        name=args.name,
        project=str(REPO_ROOT / "runs"),
        exist_ok=True,
    )

    best = Path(results.save_dir) / "weights" / "best.pt"
    if best.is_file():
        dst = REPO_ROOT / "models" / "component_detector.pt"
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(best, dst)
        print(f"\nbest weights -> {dst}")
        print("enable in the app:  AOI_YOLO_MODEL_PATH=models/component_detector.pt")
        print("then evaluate:      py scripts/eval_detector.py --data", args.data, "--weights", dst)
    else:
        print(f"training finished but no best.pt at {best}")


if __name__ == "__main__":
    main()
