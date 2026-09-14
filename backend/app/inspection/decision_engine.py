"""Stage G — combine all evidence into GOOD / DEFECTIVE / REVIEW.

Rules (in order, first match wins):

    alignment failed            -> REVIEW  (ALIGNMENT_FAILED)
    image quality failed        -> REVIEW  (POOR_IMAGE_QUALITY)
    any critical defect present  -> DEFECTIVE (CRITICAL_DEFECT)
    any visual anomaly defect    -> DEFECTIVE (VISUAL_ANOMALY)
    overall confidence too low   -> REVIEW  (LOW_CONFIDENCE)
    borderline region SSIM       -> REVIEW  (CONTRADICTORY)
    otherwise                    -> GOOD

Uncertainty is never promoted to GOOD.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..config import Settings
from ..schemas.defect import CRITICAL_DEFECTS, Defect, DefectType
from ..schemas.inspection import (
    AlignmentMetadata,
    InspectionStatus,
    QualityReport,
    ReasonCode,
    RegionMeasurement,
)


@dataclass
class Decision:
    status: InspectionStatus
    reason: ReasonCode
    explanation: str
    overall_confidence: float


def _confidence(
    alignment: AlignmentMetadata,
    quality: QualityReport,
    measurements: list[RegionMeasurement],
    defects: list[Defect],
) -> float:
    """Aggregate confidence in the *verdict* (not in any single defect)."""
    parts: list[float] = []

    if alignment.success:
        # error 0px -> 1.0, error == threshold -> ~0.6
        parts.append(max(0.5, 1.0 - alignment.alignment_error_px / 6.0))
    else:
        parts.append(0.3)

    parts.append(1.0 if quality.passed else 0.4)

    if measurements:
        found = [m for m in measurements if m.found]
        if found:
            parts.append(sum(m.ssim for m in found) / len(found))
        parts.append(len(found) / len(measurements))

    if defects:
        parts.append(sum(d.confidence for d in defects) / len(defects))

    return round(max(0.0, min(1.0, sum(parts) / len(parts))), 3)


def decide(
    alignment: AlignmentMetadata,
    quality: QualityReport,
    measurements: list[RegionMeasurement],
    defects: list[Defect],
    cfg: Settings,
    board_similarity: float = 0.0,
) -> Decision:
    conf = _confidence(alignment, quality, measurements, defects)

    if not alignment.success:
        return Decision(
            InspectionStatus.REVIEW,
            ReasonCode.ALIGNMENT_FAILED,
            f"Could not align board to the reference: {alignment.reason or 'unknown'}. "
            "No pass/fail decision was made.",
            conf,
        )

    if not quality.passed:
        return Decision(
            InspectionStatus.REVIEW,
            ReasonCode.POOR_IMAGE_QUALITY,
            "Image quality is inadequate for inspection: " + "; ".join(quality.issues),
            conf,
        )

    # Registration-trust guard: "success" alignment but the board barely matches
    # the reference and most regions read as missing => misregistration, not a
    # real defect. Never let this become DEFECTIVE or GOOD.
    if measurements and 0.0 < board_similarity < cfg.decision_min_board_ssim:
        missing = sum(1 for m in measurements if not m.found)
        if missing / len(measurements) > 0.5:
            return Decision(
                InspectionStatus.REVIEW,
                ReasonCode.CONTRADICTORY,
                f"Alignment reported success but the aligned board only weakly matches "
                f"the reference (SSIM {board_similarity:.2f}) and {missing}/{len(measurements)} "
                "components read as missing — registration is not trustworthy, manual "
                "review required.",
                min(conf, 0.5),
            )

    critical = [d for d in defects if d.type in CRITICAL_DEFECTS]
    # A deterministic MISSING/SHIFTED/ROTATED call that the object detector
    # actively contradicts is not decided here — it goes to a human.
    # (WRONG_COMPONENT comes *from* the detector, so it is never "contradicted".)
    conflicted = {
        m.name for m in measurements if m.detector_agreement == "conflict"
    }
    unresolved = [
        d for d in critical
        if d.type == DefectType.WRONG_COMPONENT or d.component not in conflicted
    ]
    if critical and not unresolved:
        names = ", ".join(sorted({d.component for d in critical}))
        return Decision(
            InspectionStatus.REVIEW,
            ReasonCode.CONTRADICTORY,
            f"Template comparison and the object detector disagree at {names} — "
            "manual review required.",
            min(conf, 0.5),
        )
    if unresolved:
        names = ", ".join(
            f"{d.component} ({d.type.value.replace('_', ' ').lower()})" for d in unresolved
        )
        return Decision(
            InspectionStatus.DEFECTIVE,
            ReasonCode.CRITICAL_DEFECT,
            f"{len(unresolved)} component defect(s) beyond tolerance: {names}.",
            conf,
        )

    anomalies = [d for d in defects if d.type == DefectType.VISUAL_ANOMALY]
    if anomalies:
        names = ", ".join(d.component for d in anomalies)
        return Decision(
            InspectionStatus.DEFECTIVE,
            ReasonCode.VISUAL_ANOMALY,
            f"Strong visual difference from reference at: {names}.",
            conf,
        )

    if conf < cfg.decision_min_confidence:
        return Decision(
            InspectionStatus.REVIEW,
            ReasonCode.LOW_CONFIDENCE,
            f"Inspection completed but overall confidence ({conf:.2f}) is below the "
            f"configured threshold ({cfg.decision_min_confidence:.2f}).",
            conf,
        )

    borderline = [
        m for m in measurements
        if m.found and cfg.region_ssim_anomaly <= m.ssim < cfg.region_ssim_review
    ]
    if borderline:
        names = ", ".join(m.name for m in borderline)
        return Decision(
            InspectionStatus.REVIEW,
            ReasonCode.CONTRADICTORY,
            f"Region(s) {names} are a borderline visual match — manual review advised.",
            conf,
        )

    return Decision(
        InspectionStatus.GOOD,
        ReasonCode.OK,
        "All required components present, within position and rotation tolerance, "
        "and visually consistent with the reference.",
        conf,
    )
