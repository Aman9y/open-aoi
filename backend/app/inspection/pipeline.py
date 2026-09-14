"""Engine orchestration: image + profile -> InspectionResult (+ saved media).

Stages: A presence + board detection/crop · B image quality · C alignment ·
D/E/F region measurement + defects · G decision. Every run writes
original / cropped / aligned / annotated / montage PNGs and result.json under
``outputs/<inspection_id>/``.
"""

from __future__ import annotations

import datetime as dt
import time
import uuid
from pathlib import Path

import cv2
import numpy as np

from ..config import Settings
from ..logging_config import get_logger
from ..profiles.base import InspectionProfile
from ..models import MODEL_NOT_CONFIGURED, build_component_detector
from ..schemas.defect import Defect, DefectType
from ..schemas.inspection import (
    AlignmentMetadata,
    BoardDetection,
    InspectionResult,
    InspectionStatus,
    ModelStatus,
    QualityReport,
    ReasonCode,
)
from ..schemas.reference import InspectionMode
from . import (
    alignment,
    component_match,
    decision_engine,
    defect_detector,
    detection,
    preprocessing,
    reference_checker,
    surface_check,
)
from .visualization import annotate, montage

log = get_logger(__name__)


def _new_id() -> str:
    return "INS-" + dt.datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]


def _imwrite(path: Path, img: np.ndarray) -> None:
    ok, buf = cv2.imencode(".png", img)
    if ok:
        path.write_bytes(buf.tobytes())




def run_inspection(
    image_bgr: np.ndarray,
    profile: InspectionProfile,
    cfg: Settings,
    *,
    original_filename: str = "",
) -> InspectionResult:
    t0 = time.perf_counter()
    inspection_id = _new_id()
    out_dir = cfg.outputs_dir / inspection_id
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")

    def media_url(name: str) -> str:
        return f"/media/outputs/{inspection_id}/{name}"

    partial = dict(
        inspection_id=inspection_id, timestamp=ts, reference_id=profile.id,
        profile_kind=profile.kind.value,
        model_status=ModelStatus.DETERMINISTIC_ONLY,
        original_image_path=media_url("original.png"),
    )

    def finish(**kw) -> InspectionResult:
        kw.setdefault("inspection_time_ms", int((time.perf_counter() - t0) * 1000))
        result = InspectionResult(**{**partial, **kw})
        (out_dir / "result.json").write_text(result.model_dump_json(indent=2), "utf-8")
        log.info(
            "%s -> %s (%s) conf=%.2f %dms defects=%d",
            inspection_id, result.status.value, result.reason.value,
            result.overall_confidence, result.inspection_time_ms, len(result.defects),
        )
        return result

    # ---- Stage A.1: decode sanity --------------------------------------
    original = preprocessing.resize_max(image_bgr, cfg.image_max_dim)
    _imwrite(out_dir / "original.png", original)

    if not preprocessing.is_probably_valid_image(original):
        return finish(
            status=InspectionStatus.REVIEW, reason=ReasonCode.INVALID_IMAGE,
            explanation="No valid image received (too small or empty).",
            overall_confidence=0.15,
            quality=QualityReport(passed=False, blur_score=0, brightness=0, contrast=0,
                                  overexposed_frac=0, issues=["invalid image"]),
            alignment=AlignmentMetadata(success=False, reason="not run"),
        )

    ref_bgr = preprocessing.resize_max(profile.load_reference_image(), cfg.image_max_dim)
    ref_aspect = ref_bgr.shape[1] / ref_bgr.shape[0]

    # ---- Stage A.2: board detection / crop ----------------------------
    working, det = detection.detect_board(original, cfg, ref_aspect)
    _imwrite(out_dir / "cropped.png", working)

    # ---- Stage B: image quality (on the working crop) -----------------
    quality = preprocessing.quality_check(working, cfg)

    # ---- SURFACE MODE: whole-object comparison, no component regions ----
    if profile.inspection_mode == InspectionMode.SURFACE:
        return _run_surface(
            profile, ref_bgr, original, working, det, quality, out_dir, media_url, finish, cfg
        )

    # ---- Stage C: alignment ------------------------------------------------
    aligned_bgr, align_meta = alignment.align_to_reference(working, ref_bgr, cfg)
    _imwrite(out_dir / "aligned.png", aligned_bgr)
    board_sim = (
        round(alignment.board_ssim(aligned_bgr, ref_bgr), 4) if align_meta.success else 0.0
    )

    # ---- Stages D/E/F: region measurement + defects ------------------
    measurements: list = []
    defects: list = []
    detections: list = []
    model_status = ModelStatus.DETERMINISTIC_ONLY
    heatmap = None
    if align_meta.success and quality.passed:
        if profile.regions:
            measurements = reference_checker.measure_all(profile.regions, aligned_bgr, ref_bgr, cfg)
            defects = defect_detector.detect_all(
                profile.regions, measurements, cfg,
                profile.mm_per_px or cfg.mm_per_px, board_sim,
            )

            # ---- Stage F.5: optional object-detector (YOLO) corroboration ----
            detector = build_component_detector(cfg)
            if detector.status == MODEL_NOT_CONFIGURED and cfg.yolo_model_path:
                model_status = ModelStatus.MODEL_NOT_CONFIGURED
            elif detector.status != MODEL_NOT_CONFIGURED:
                raw = detector.detect(aligned_bgr)
                measurements, extra, detections = component_match.fuse(
                    profile.regions, measurements, raw, cfg
                )
                defects = defects + extra
                model_status = ModelStatus.YOLO_ACTIVE

        heatmap = reference_checker.difference_heatmap(aligned_bgr, ref_bgr)

    # ---- Stage G: decision -----------------------------------------------
    decision = decision_engine.decide(
        align_meta, quality, measurements, defects, cfg, board_sim
    )

    annotated = annotate(
        aligned_bgr, decision.status, measurements, defects, heatmap, detections
    )
    _imwrite(out_dir / "annotated.png", annotated)
    _imwrite(
        out_dir / "montage.png",
        montage(
            [original, working, aligned_bgr, annotated],
            ["original", f"cropped ({det.method})", "aligned", decision.status.value],
        ),
    )

    return finish(
        status=decision.status,
        reason=decision.reason,
        explanation=decision.explanation,
        overall_confidence=decision.overall_confidence,
        quality=quality,
        detection=det,
        alignment=align_meta,
        board_similarity=board_sim,
        regions=measurements,
        detections=detections,
        defects=defects,
        model_status=model_status,
        cropped_image_path=media_url("cropped.png"),
        aligned_image_path=media_url("aligned.png"),
        annotated_image_path=media_url("annotated.png"),
        montage_image_path=media_url("montage.png"),
    )


def _run_surface(
    profile, ref_bgr, original, working, det, quality, out_dir, media_url, finish, cfg
) -> InspectionResult:
    """Whole-object surface comparison (InspectionMode.SURFACE)."""
    # Both the reference and the test frame must be reduced to *just the object*,
    # or the (identical) background inflates the similarity and a defect slips
    # through. detect_board's quad finder grabs furniture (a laptop, a mat), so
    # surface mode uses the centre-biased edge-cluster bbox instead.
    def _object_only(img: np.ndarray) -> tuple[np.ndarray, bool]:
        bb = detection.object_bbox(img)
        if bb is not None:
            x, y, bw, bh = bb
            return img[y : y + bh, x : x + bw], True
        return surface_check.center_crop(img, 0.6), False

    ref_obj, ref_found = _object_only(ref_bgr)
    test_obj, test_found = _object_only(original)
    obj_located = ref_found and test_found

    sr = surface_check.inspect_surface(test_obj, ref_obj, cfg)
    _imwrite(out_dir / "cropped.png", test_obj)
    _imwrite(out_dir / "aligned.png", sr.aligned_bgr)

    det = BoardDetection(
        found=obj_located,
        method="object" if obj_located else "centre-crop",
        note="" if obj_located
        else "object not clearly located — comparing the centre of the frame; "
        "fill more of the frame with the object or use a plainer background",
    )
    align_meta = AlignmentMetadata(
        success=True, alignment_error_px=round(max(0.0, (1 - sr.ssim) * 6), 2),
        reason="surface registration",
    )

    # Surface mode: a plain uniform object legitimately reads as "low sharpness /
    # low contrast / bright". Only genuinely unusable frames (too dark, or almost
    # entirely blown out) fail the gate here.
    surface_quality_ok = (
        quality.brightness >= cfg.quality_brightness_min
        and quality.overexposed_frac <= 0.55
    )

    defects: list[Defect] = []
    pct = sr.diff_frac * 100
    if not surface_quality_ok:
        status, reason = InspectionStatus.REVIEW, ReasonCode.POOR_IMAGE_QUALITY
        issue = "image too dark" if quality.brightness < cfg.quality_brightness_min else "image blown out"
        explanation = f"Image quality inadequate: {issue}."
        conf = 0.4
    elif sr.ssim < cfg.surface_defect_ssim:
        status, reason = InspectionStatus.DEFECTIVE, ReasonCode.VISUAL_ANOMALY
        explanation = (
            f"Surface does not match the reference (similarity {sr.ssim:.2f}, "
            f"{pct:.0f}% of the object differs) — damage, contamination, wrong item or misprint."
        )
        conf = round(min(0.99, 0.6 + (cfg.surface_defect_ssim - sr.ssim)), 3)
        h, w = sr.aligned_bgr.shape[:2]
        defects.append(
            Defect(
                component="SURFACE", type=DefectType.VISUAL_ANOMALY, confidence=conf,
                expected="Surface matches the known-good reference",
                observed=f"similarity {sr.ssim:.2f}, {pct:.0f}% of the surface differs",
                bbox=(0, 0, w, h),
            )
        )
    elif sr.ssim < cfg.surface_review_ssim:
        status, reason = InspectionStatus.REVIEW, ReasonCode.CONTRADICTORY
        explanation = (
            f"Surface is a borderline match (similarity {sr.ssim:.2f}) — manual review advised."
        )
        conf = 0.55
    else:
        status, reason = InspectionStatus.GOOD, ReasonCode.OK
        explanation = f"Surface matches the known-good reference (similarity {sr.ssim:.2f})."
        conf = round(min(0.99, 0.75 + (sr.ssim - cfg.surface_review_ssim)), 3)

    annotated = annotate(sr.aligned_bgr, status, [], defects, sr.heatmap, None)
    _imwrite(out_dir / "annotated.png", annotated)
    _imwrite(
        out_dir / "montage.png",
        montage(
            [original, working, sr.aligned_bgr, annotated],
            ["original", f"cropped ({det.method})", "aligned", status.value],
        ),
    )

    return finish(
        status=status, reason=reason, explanation=explanation, overall_confidence=conf,
        quality=quality, detection=det, alignment=align_meta,
        board_similarity=sr.ssim, regions=[], detections=[], defects=defects,
        model_status=ModelStatus.DETERMINISTIC_ONLY,
        cropped_image_path=media_url("cropped.png"),
        aligned_image_path=media_url("aligned.png"),
        annotated_image_path=media_url("annotated.png"),
        montage_image_path=media_url("montage.png"),
    )
