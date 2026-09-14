"""Stages D/E/F — per-region comparison of the aligned image against the reference.

Fully deterministic (OpenCV + SSIM). No ML. Each region yields a
:class:`RegionMeasurement` with the raw numbers; turning those into typed defects
is :mod:`defect_detector`'s job.
"""

from __future__ import annotations

import cv2
import numpy as np
from skimage.metrics import structural_similarity as ssim

from ..config import Settings
from ..schemas.inspection import RegionMeasurement
from ..schemas.reference import Region


def _clamp_box(x: int, y: int, w: int, h: int, W: int, H: int) -> tuple[int, int, int, int]:
    x0 = max(0, min(x, W - 1))
    y0 = max(0, min(y, H - 1))
    x1 = max(x0 + 1, min(x + w, W))
    y1 = max(y0 + 1, min(y + h, H))
    return x0, y0, x1 - x0, y1 - y0


def _rotate_patch(patch: np.ndarray, angle: float) -> np.ndarray:
    h, w = patch.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), angle, 1.0)
    return cv2.warpAffine(patch, m, (w, h), flags=cv2.INTER_LINEAR,
                          borderMode=cv2.BORDER_REPLICATE)


def _best_match(
    search: np.ndarray, ref_patch: np.ndarray, check_rotation: bool
) -> tuple[float, tuple[int, int], float]:
    """Return (peak_corr, top_left_in_search, coarse_angle_deg).

    Plain template matching first; if that is weak and rotation is allowed, retry
    with the template rotated over a small angle sweep so a rotated-but-present
    component is not misreported as missing.
    """
    res = cv2.matchTemplate(search, ref_patch, cv2.TM_CCOEFF_NORMED)
    _, peak, _, loc = cv2.minMaxLoc(res)
    best = (float(peak), (int(loc[0]), int(loc[1])), 0.0)

    if check_rotation and best[0] < 0.75:
        for angle in (-24, -18, -12, -8, 8, 12, 18, 24):
            r = cv2.matchTemplate(search, _rotate_patch(ref_patch, angle), cv2.TM_CCOEFF_NORMED)
            _, p, _, l = cv2.minMaxLoc(r)
            if p > best[0]:
                best = (float(p), (int(l[0]), int(l[1])), float(angle))
    return best


def _estimate_rotation(ref_patch: np.ndarray, test_patch: np.ndarray) -> float:
    """Rotation (deg) of test_patch relative to ref_patch via ECC. 0.0 on failure."""
    if ref_patch.shape != test_patch.shape or min(ref_patch.shape) < 12:
        return 0.0
    try:
        warp = np.eye(2, 3, dtype=np.float32)
        crit = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 50, 1e-4)
        cv2.findTransformECC(
            ref_patch.astype(np.float32),
            test_patch.astype(np.float32),
            warp,
            cv2.MOTION_EUCLIDEAN,
            crit,
            None,
            5,
        )
        return float(np.degrees(np.arctan2(warp[1, 0], warp[0, 0])))
    except cv2.error:
        return 0.0


def measure_region(
    region: Region,
    aligned_gray: np.ndarray,
    ref_gray: np.ndarray,
    cfg: Settings,
) -> RegionMeasurement:
    H, W = ref_gray.shape[:2]
    rx, ry, rw, rh = _clamp_box(*region.bbox, W, H)
    ref_patch = ref_gray[ry : ry + rh, rx : rx + rw]

    margin = region.tolerances.search_margin_px or cfg.region_search_margin_px
    sx, sy, sw, sh = _clamp_box(rx - margin, ry - margin, rw + 2 * margin, rh + 2 * margin, W, H)
    search = aligned_gray[sy : sy + sh, sx : sx + sw]

    expected_center = region.center

    if search.shape[0] < ref_patch.shape[0] or search.shape[1] < ref_patch.shape[1]:
        return RegionMeasurement(
            name=region.name,
            found=False,
            peak_corr=0.0,
            offset_px=0.0,
            rotation_deg=0.0,
            ssim=0.0,
            expected_center=expected_center,
            observed_center=None,
            bbox=(rx, ry, rw, rh),
        )

    check_rotation = region.tolerances.check_rotation
    peak, max_loc, coarse_angle = _best_match(search, ref_patch, check_rotation)

    obs_x = sx + max_loc[0]
    obs_y = sy + max_loc[1]
    observed_center = (obs_x + rw / 2.0, obs_y + rh / 2.0)
    offset = float(np.hypot(observed_center[0] - expected_center[0],
                            observed_center[1] - expected_center[1]))

    missing_corr = region.tolerances.missing_corr or cfg.region_missing_corr
    found = peak >= missing_corr

    test_patch = aligned_gray[obs_y : obs_y + rh, obs_x : obs_x + rw]
    rotation = 0.0
    region_ssim = 0.0
    if found and test_patch.shape == ref_patch.shape:
        if check_rotation:
            fine = _estimate_rotation(ref_patch, test_patch)
            # Prefer the ECC estimate when it agrees in sign / is plausible,
            # otherwise fall back to the coarse sweep result.
            rotation = fine if abs(fine) >= abs(coarse_angle) * 0.5 or coarse_angle == 0 else coarse_angle
        win = min(7, rw - (rw % 2 == 0), rh - (rh % 2 == 0))
        if win >= 3:
            region_ssim = float(
                ssim(ref_patch, test_patch, win_size=win if win % 2 else win - 1)
            )
        else:
            region_ssim = float(peak)

    return RegionMeasurement(
        name=region.name,
        found=found,
        peak_corr=round(float(peak), 4),
        offset_px=round(offset, 2),
        rotation_deg=round(rotation, 2),
        ssim=round(region_ssim, 4),
        expected_center=(round(expected_center[0], 1), round(expected_center[1], 1)),
        observed_center=(
            (round(observed_center[0], 1), round(observed_center[1], 1)) if found else None
        ),
        bbox=(rx, ry, rw, rh),
    )


def _color_delta(region: Region, aligned_bgr: np.ndarray, ref_bgr: np.ndarray) -> float:
    """Perceptual (CIELAB) distance between the mean colour of a region in the
    aligned image vs the reference. Catches a wrong-colour part that grayscale
    template matching / SSIM would miss."""
    H, W = ref_bgr.shape[:2]
    x, y, w, h = _clamp_box(*region.bbox, W, H)
    a = cv2.cvtColor(aligned_bgr[y : y + h, x : x + w], cv2.COLOR_BGR2LAB).reshape(-1, 3).mean(0)
    b = cv2.cvtColor(ref_bgr[y : y + h, x : x + w], cv2.COLOR_BGR2LAB).reshape(-1, 3).mean(0)
    return float(np.linalg.norm(a - b))


def measure_all(
    regions: list[Region], aligned_bgr: np.ndarray, ref_bgr: np.ndarray, cfg: Settings
) -> list[RegionMeasurement]:
    aligned_gray = cv2.cvtColor(aligned_bgr, cv2.COLOR_BGR2GRAY)
    ref_gray = cv2.cvtColor(ref_bgr, cv2.COLOR_BGR2GRAY)
    out = []
    for r in regions:
        m = measure_region(r, aligned_gray, ref_gray, cfg)
        if m.found:
            m.color_delta = round(_color_delta(r, aligned_bgr, ref_bgr), 2)
        out.append(m)
    return out


def difference_heatmap(aligned_bgr: np.ndarray, ref_bgr: np.ndarray) -> np.ndarray:
    """Normalized absolute-difference map (uint8, single channel) for visualization."""
    a = cv2.GaussianBlur(cv2.cvtColor(aligned_bgr, cv2.COLOR_BGR2GRAY), (5, 5), 0)
    b = cv2.GaussianBlur(cv2.cvtColor(ref_bgr, cv2.COLOR_BGR2GRAY), (5, 5), 0)
    diff = cv2.absdiff(a, b)
    return cv2.normalize(diff, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
