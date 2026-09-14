"""Turn raw :class:`RegionMeasurement`s into typed, explainable :class:`Defect`s.

Confidence here is a **calibrated heuristic**, not a model probability: it scales
with the margin between the measured value and the configured tolerance. This is
documented behaviour, not a fabricated AI score.
"""

from __future__ import annotations

from ..config import Settings
from ..schemas.defect import Defect, DefectType
from ..schemas.inspection import RegionMeasurement
from ..schemas.reference import Region


def _margin_confidence(measured: float, tolerance: float, *, floor: float = 0.55) -> float:
    """Map how far past tolerance a measurement is to a 0.55-0.99 confidence."""
    if tolerance <= 0:
        return 0.9
    over = (measured - tolerance) / tolerance
    return round(min(0.99, max(floor, floor + (0.99 - floor) * min(over, 1.0))), 3)


def _shortfall_confidence(value: float, threshold: float, *, floor: float = 0.55) -> float:
    """Confidence that ``value`` is meaningfully *below* ``threshold``."""
    if threshold <= 0:
        return 0.9
    short = (threshold - value) / threshold
    return round(min(0.99, max(floor, floor + (0.99 - floor) * min(short, 1.0))), 3)


def _bbox_xyxy(x: int, y: int, w: int, h: int) -> tuple[int, int, int, int]:
    return (int(x), int(y), int(x + w), int(y + h))


def detect_region_defects(
    region: Region, m: RegionMeasurement, cfg: Settings, mm_per_px: float = 0.0,
    board_similarity: float = 1.0,
) -> list[Defect]:
    tol = region.tolerances
    pos_tol = tol.position_tol_px if tol.position_tol_px is not None else cfg.region_position_tol_px
    rot_tol = tol.rotation_tol_deg if tol.rotation_tol_deg is not None else cfg.region_rotation_tol_deg
    missing_corr = tol.missing_corr if tol.missing_corr is not None else cfg.region_missing_corr
    ssim_anomaly = tol.ssim_anomaly if tol.ssim_anomaly is not None else cfg.region_ssim_anomaly

    x, y, w, h = m.bbox
    defects: list[Defect] = []

    if not m.found:
        defects.append(
            Defect(
                component=region.name,
                type=DefectType.MISSING_COMPONENT,
                confidence=_shortfall_confidence(m.peak_corr, missing_corr, floor=0.7),
                expected="Component present at reference location",
                observed=f"No matching component detected (match score {m.peak_corr:.2f} < {missing_corr:.2f})",
                expected_position=m.expected_center,
                actual_position=None,
                allowed_px=pos_tol,
                bbox=_bbox_xyxy(x, y, w, h),
            )
        )
        return defects  # position/rotation meaningless if it isn't there

    if m.offset_px > pos_tol:
        dev_mm = round(m.offset_px * mm_per_px, 3) if mm_per_px > 0 else None
        defects.append(
            Defect(
                component=region.name,
                type=DefectType.SHIFTED_COMPONENT,
                confidence=_margin_confidence(m.offset_px, pos_tol),
                expected=f"Centre within {pos_tol:.1f}px of {m.expected_center}",
                observed=f"Centre at {m.observed_center}, offset {m.offset_px:.1f}px",
                expected_position=m.expected_center,
                actual_position=m.observed_center,
                deviation_px=m.offset_px,
                deviation_mm=dev_mm,
                allowed_px=pos_tol,
                bbox=_bbox_xyxy(
                    int(m.observed_center[0] - w / 2),
                    int(m.observed_center[1] - h / 2),
                    w,
                    h,
                ),
            )
        )

    if region.tolerances.check_rotation and abs(m.rotation_deg) > rot_tol:
        defects.append(
            Defect(
                component=region.name,
                type=DefectType.ROTATED_COMPONENT,
                confidence=_margin_confidence(abs(m.rotation_deg), rot_tol),
                expected=f"Orientation within +/-{rot_tol:.1f} deg",
                observed=f"Rotated {m.rotation_deg:+.1f} deg",
                expected_position=m.expected_center,
                actual_position=m.observed_center,
                rotation_deg=m.rotation_deg,
                allowed_rotation_deg=rot_tol,
                bbox=_bbox_xyxy(x, y, w, h),
            )
        )

    # Visual anomaly — only if geometry looked OK. A single region with a
    # borderline SSIM but a solid template match and matching colour is
    # alignment noise, not a defect: require the SSIM drop to be clear, or a
    # second signal (template correlation or colour) to corroborate it. And the
    # SSIM/colour signals are only trusted when the board is well registered
    # (otherwise the case goes to REVIEW, not DEFECTIVE).
    reliable = board_similarity >= cfg.region_anomaly_min_board_ssim
    blatant_color = m.color_delta > cfg.region_color_delta_max * 1.6
    color_bad = m.color_delta > cfg.region_color_delta_max
    clear_ssim_fail = m.ssim < ssim_anomaly * 0.78
    corroborated = m.peak_corr < 0.70 or color_bad
    anomaly = blatant_color or (
        reliable and (clear_ssim_fail or (m.ssim < ssim_anomaly and corroborated) or color_bad)
    )
    if not defects and anomaly:
        if color_bad and m.ssim >= ssim_anomaly:
            expected = "Region colour matches reference"
            observed = f"Colour differs from reference (ΔE {m.color_delta:.0f})"
            conf = _margin_confidence(m.color_delta, cfg.region_color_delta_max)
        else:
            expected = f"Region visually matches reference (SSIM >= {ssim_anomaly:.2f})"
            observed = f"Region differs from reference (SSIM {m.ssim:.2f}" + (
                f", ΔE {m.color_delta:.0f})" if color_bad else ")"
            )
            conf = _shortfall_confidence(m.ssim, ssim_anomaly)
        defects.append(
            Defect(
                component=region.name,
                type=DefectType.VISUAL_ANOMALY,
                confidence=conf,
                expected=expected,
                observed=observed,
                expected_position=m.expected_center,
                actual_position=m.observed_center,
                bbox=_bbox_xyxy(x, y, w, h),
            )
        )

    return defects


def detect_all(
    regions: list[Region],
    measurements: list[RegionMeasurement],
    cfg: Settings,
    mm_per_px: float = 0.0,
    board_similarity: float = 1.0,
) -> list[Defect]:
    by_name = {m.name: m for m in measurements}
    out: list[Defect] = []
    for region in regions:
        m = by_name.get(region.name)
        if m is not None:
            out.extend(detect_region_defects(region, m, cfg, mm_per_px, board_similarity))
    return out
