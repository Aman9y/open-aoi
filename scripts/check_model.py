"""Verify a downloaded YOLO model and show how to wire its classes in.

    # put the .pt where the app looks, then:
    set  AOI_YOLO_MODEL_PATH=models/component_detector.pt      (Windows)
    export AOI_YOLO_MODEL_PATH=models/component_detector.pt    (bash)

    py scripts/check_model.py
    py scripts/check_model.py --image data/datasets/synthetic_v1/images/good_01.png

Prints the model's class names, runs one inference, and suggests an
AOI_YOLO_CLASS_ALIASES mapping so the detector's vocabulary lines up with the
`expected_class` values in your references (resistor / cap / ic / led / connector).
Needs: pip install -r backend/requirements-ml.txt
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import _bootstrap  # noqa: F401

from app.config import get_settings

_CANON = ("resistor", "cap", "ic", "led", "connector")
_HINTS = {
    "resistor": ["r", "res", "resistor"],
    "cap": ["c", "cap", "capacitor", "electrolytic", "smd_cap"],
    "ic": ["u", "ic", "chip", "qfp", "soic", "bga", "microcontroller"],
    "led": ["d", "led", "diode"],
    "connector": ["j", "conn", "connector", "header", "pin_header", "socket", "usb"],
}


def _guess(label: str) -> str | None:
    low = label.lower()
    for canon, keys in _HINTS.items():
        if low in keys or any(k in low for k in keys):
            return canon
    return None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", type=Path, help="override AOI_YOLO_MODEL_PATH")
    ap.add_argument("--image", type=Path, help="run inference on this image")
    ap.add_argument("--conf", type=float, default=0.25)
    args = ap.parse_args()

    cfg = get_settings()
    model_path = args.model or cfg.yolo_model_path
    if not model_path:
        raise SystemExit(
            "No model path. Set AOI_YOLO_MODEL_PATH or pass --model.\n"
            "Drop your downloaded .pt at  models/component_detector.pt"
        )
    if not Path(model_path).is_file():
        raise SystemExit(f"not found: {model_path}")

    try:
        from ultralytics import YOLO
    except ImportError:
        raise SystemExit("ultralytics not installed.  pip install -r backend/requirements-ml.txt")

    model = YOLO(str(model_path))
    names = dict(model.names)
    print(f"model      : {model_path}")
    print(f"task       : {getattr(model, 'task', '?')}")
    print(f"classes ({len(names)}): {list(names.values())}")

    aliases = {}
    print("\nsuggested AOI_YOLO_CLASS_ALIASES (edit as needed):")
    for label in names.values():
        g = _guess(str(label))
        aliases[str(label)] = g or str(label)
        flag = "" if g else "   <-- no obvious match, set manually or leave as-is"
        print(f"  {label!r:>22}: {(g or label)!r}{flag}")
    print("\n  " + json.dumps(aliases))

    if args.image:
        if not args.image.is_file():
            raise SystemExit(f"image not found: {args.image}")
        res = model.predict(str(args.image), conf=args.conf, verbose=False)[0]
        print(f"\ninference on {args.image.name}: {len(res.boxes)} detections")
        for b in res.boxes:
            xyxy = [int(v) for v in b.xyxy[0].tolist()]
            print(f"  {names[int(b.cls[0])]:>16}  {float(b.conf[0]):.2f}  bbox={xyxy}")
        if not len(res.boxes):
            print("  (nothing detected — try a lower --conf, or the model may expect a"
                  " different input domain than this image)")

    print("\nenable:  AOI_YOLO_MODEL_PATH=" + str(model_path))
    if any(a == b for a, b in aliases.items()) and set(aliases.values()) - set(_CANON):
        print("note: some classes did not map to the reference vocabulary "
              f"{_CANON} — the WRONG_COMPONENT check only runs where classes match.")


if __name__ == "__main__":
    main()
