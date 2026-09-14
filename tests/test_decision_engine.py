"""Decision engine truth table — isolated from imaging."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.config import Settings
from app.inspection.decision_engine import decide
from app.schemas.defect import Defect, DefectType
from app.schemas.inspection import (
    AlignmentMetadata,
    InspectionStatus,
    QualityReport,
    ReasonCode,
    RegionMeasurement,
)

CFG = Settings()
OK_ALIGN = AlignmentMetadata(success=True, alignment_error_px=0.5, inliers=200)
OK_QUALITY = QualityReport(passed=True, blur_score=200, brightness=120, contrast=45,
                           overexposed_frac=0.0)


def _m(name: str, ssim: float = 0.95) -> RegionMeasurement:
    return RegionMeasurement(name=name, found=True, peak_corr=0.9, offset_px=1.0,
                             rotation_deg=0.5, ssim=ssim, expected_center=(10, 10),
                             observed_center=(10, 10), bbox=(0, 0, 20, 20))


def test_all_pass_is_good():
    d = decide(OK_ALIGN, OK_QUALITY, [_m("R1"), _m("R2")], [], CFG)
    assert d.status == InspectionStatus.GOOD and d.reason == ReasonCode.OK


def test_critical_defect_is_defective():
    defect = Defect(component="R1", type=DefectType.MISSING_COMPONENT, confidence=0.9,
                    expected="present", observed="absent")
    d = decide(OK_ALIGN, OK_QUALITY, [_m("R1")], [defect], CFG)
    assert d.status == InspectionStatus.DEFECTIVE
    assert d.reason == ReasonCode.CRITICAL_DEFECT


def test_alignment_failure_is_review():
    d = decide(AlignmentMetadata(success=False, reason="no inliers"), OK_QUALITY, [], [], CFG)
    assert d.status == InspectionStatus.REVIEW
    assert d.reason == ReasonCode.ALIGNMENT_FAILED


def test_poor_quality_is_review():
    bad = QualityReport(passed=False, blur_score=5, brightness=120, contrast=10,
                        overexposed_frac=0.0, issues=["image is blurred"])
    d = decide(OK_ALIGN, bad, [], [], CFG)
    assert d.status == InspectionStatus.REVIEW
    assert d.reason == ReasonCode.POOR_IMAGE_QUALITY


def test_borderline_visual_match_is_review_not_good():
    # SSIM sits in the (anomaly, review) band -> not clearly good, not clearly bad.
    band = (CFG.region_ssim_anomaly + CFG.region_ssim_review) / 2
    d = decide(OK_ALIGN, OK_QUALITY, [_m("R1", ssim=band), _m("R2", ssim=0.95)], [], CFG)
    assert d.status == InspectionStatus.REVIEW
    assert d.reason == ReasonCode.CONTRADICTORY


def test_low_confidence_is_review_not_good():
    # With a strict confidence threshold, an uncertain-but-not-failed alignment
    # plus weak region matches must fall to REVIEW, never GOOD.
    strict = Settings(decision_min_confidence=0.95)
    shaky = AlignmentMetadata(success=True, alignment_error_px=2.9, inliers=26)
    d = decide(shaky, OK_QUALITY, [_m("R1", ssim=0.80)], [], strict)
    assert d.status == InspectionStatus.REVIEW
    assert d.reason == ReasonCode.LOW_CONFIDENCE
