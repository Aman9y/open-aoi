"""Local demo / CLI.

    python -m app.demo --image data/test/defect_missing_R17.png
    python -m app.demo --image path/to.jpg --reference PCB_MODEL_001
    python -m app.demo --camera 0
    python -m app.demo --stream http://192.168.1.42:8080/video

Writes original / aligned / annotated / result.json under ``outputs/<id>/`` and
prints a human-readable summary. No fake predictions — the engine runs for real.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")  # hush camera backend-probe chatter

import cv2  # noqa: E402

from .config import get_settings  # noqa: E402
from .inspection.pipeline import run_inspection
from .logging_config import configure_logging
from .schemas.inspection import InspectionStatus
from .sources import FileSource, SourceError
from .sources.camera_source import CameraSource, StreamSource
from .storage.inspection_repository import InspectionRepository
from .storage.reference_repository import ReferenceError, ReferenceRepository

_ICON = {
    InspectionStatus.GOOD: "[ GOOD ]",
    InspectionStatus.DEFECTIVE: "[ DEFECTIVE ]",
    InspectionStatus.REVIEW: "[ REVIEW ]",
}


def _print_result(result) -> None:
    print("\n" + "=" * 56)
    print(f" INSPECTION RESULT   {_ICON[result.status]}")
    print("=" * 56)
    print(f" id           : {result.inspection_id}")
    print(f" reference    : {result.reference_id} ({result.profile_kind})")
    print(f" reason       : {result.reason.value}")
    print(f" confidence   : {result.overall_confidence:.2f}")
    print(f" time         : {result.inspection_time_ms} ms")
    det = result.detection
    print(f" board detect : found={det.found} method={det.method} "
          f"coverage={det.coverage}{(' — ' + det.note) if det.note else ''}")
    print(f" alignment    : success={result.alignment.success} "
          f"err={result.alignment.alignment_error_px}px "
          f"rot={result.alignment.rotation_deg}deg inliers={result.alignment.inliers} "
          f"({result.alignment.reason or 'ORB homography'})")
    print(f" board match  : SSIM {result.board_similarity}")
    print(f" image quality: {'OK' if result.quality.passed else '; '.join(result.quality.issues)}")
    print(f" model        : {result.model_status.value}", end="")
    print(f" ({len(result.detections)} detections)" if result.detections else "")
    print(f"\n {result.explanation}")
    if result.defects:
        print(f"\n DEFECTS ({len(result.defects)}):")
        for d in result.defects:
            print(f"   - {d.component:<6} {d.type.value:<18} {d.confidence*100:5.1f}%")
            print(f"       expected: {d.expected}")
            print(f"       observed: {d.observed}")
    print("\n outputs:")
    for label, path in (
        ("original ", result.original_image_path),
        ("cropped  ", result.cropped_image_path),
        ("aligned  ", result.aligned_image_path),
        ("annotated", result.annotated_image_path),
        ("montage  ", result.montage_image_path),
    ):
        if path:
            print(f"   {label}: outputs/{result.inspection_id}/{path.split('/')[-1]}")
    print("=" * 56 + "\n")


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    ap = argparse.ArgumentParser(prog="app.demo")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--image", help="path to an image file")
    src.add_argument("--camera", type=int, metavar="INDEX", help="local webcam index")
    src.add_argument("--stream", help="phone / IP camera stream URL")
    ap.add_argument("--reference", default=None, help="reference id (default: active)")
    ap.add_argument("--json", action="store_true", help="print full JSON result")
    ap.add_argument("--no-save", action="store_true", help="do not record in history DB")
    args = ap.parse_args(argv)

    cfg = get_settings()
    try:
        profile = ReferenceRepository(cfg).load_profile(args.reference)
    except ReferenceError as exc:
        print(f"error: {exc}\nhint: run  py scripts/make_synthetic_pcb.py", file=sys.stderr)
        return 2

    try:
        if args.image:
            source = FileSource(args.image)
        elif args.camera is not None:
            source = CameraSource(args.camera)
        else:
            source = StreamSource(args.stream)
        with source:
            image = source.read()
    except SourceError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    result = run_inspection(image, profile, cfg)
    if not args.no_save:
        InspectionRepository(cfg).save(result)

    if args.json:
        print(json.dumps(json.loads(result.model_dump_json()), indent=2))
    else:
        _print_result(result)

    annotated = cfg.outputs_dir / result.inspection_id / "annotated.png"
    if annotated.is_file() and not args.json:
        print(f"open: {annotated}")
    return 0 if result.status != InspectionStatus.DEFECTIVE else 1


if __name__ == "__main__":
    raise SystemExit(main())
