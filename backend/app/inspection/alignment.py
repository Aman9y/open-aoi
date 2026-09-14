"""Stage C — align the test image to the reference image.

ORB feature matching + RANSAC homography. The test image is warped into the
reference coordinate frame so every downstream comparison is done in reference
pixel coordinates.
"""

from __future__ import annotations

import math

import cv2
import numpy as np
from skimage.metrics import structural_similarity as _ssim

from ..config import Settings
from ..logging_config import get_logger
from ..schemas.inspection import AlignmentMetadata

log = get_logger(__name__)


def board_ssim(aligned_bgr: np.ndarray, ref_bgr: np.ndarray) -> float:
    """Whole-frame structural similarity of an aligned image vs the reference.
    Used as an independent check that a claimed alignment is actually good."""
    a = cv2.cvtColor(aligned_bgr, cv2.COLOR_BGR2GRAY)
    b = cv2.cvtColor(ref_bgr, cv2.COLOR_BGR2GRAY)
    try:
        return float(_ssim(a, b))
    except ValueError:
        return 0.0


def _decompose(h: np.ndarray) -> tuple[float, float, tuple[float, float]]:
    """Approximate rotation (deg), uniform scale and translation from H."""
    a, b = float(h[0, 0]), float(h[0, 1])
    c, d = float(h[1, 0]), float(h[1, 1])
    sx = math.hypot(a, c)
    sy = math.hypot(b, d)
    scale = (sx + sy) / 2.0
    rotation = math.degrees(math.atan2(c, a))
    tx, ty = float(h[0, 2]), float(h[1, 2])
    return rotation, scale, (tx, ty)


def _ecc_align(
    test_bgr: np.ndarray, ref_bgr: np.ndarray, cfg: Settings, reason_prefix: str
) -> tuple[np.ndarray, AlignmentMetadata]:
    """Direct intensity-based (ECC) alignment — fallback when feature matching is
    too weak. Works when the (cropped) board already roughly overlaps the
    reference, which is the common case after stage-A rectification."""
    ref_h, ref_w = ref_bgr.shape[:2]
    fallback = cv2.resize(test_bgr, (ref_w, ref_h), interpolation=cv2.INTER_AREA)
    if not cfg.align_ecc_fallback:
        return fallback, AlignmentMetadata(success=False, reason=reason_prefix)

    scale = 480.0 / max(ref_h, ref_w)
    small = lambda im: cv2.GaussianBlur(  # noqa: E731
        cv2.resize(cv2.cvtColor(im, cv2.COLOR_BGR2GRAY), None, fx=scale, fy=scale), (5, 5), 0
    ).astype(np.float32)
    ref_s, test_s = small(ref_bgr), small(fallback)

    warp = np.eye(2, 3, dtype=np.float32)
    try:
        crit = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 200, 1e-5)
        cc, warp = cv2.findTransformECC(ref_s, test_s, warp, cv2.MOTION_AFFINE, crit, None, 5)
    except cv2.error:
        return fallback, AlignmentMetadata(success=False, reason=f"{reason_prefix}; ECC did not converge")

    # Lift the warp from the downscaled space back to full reference resolution.
    warp_full = warp.copy()
    warp_full[:, 2] /= scale
    a, b, c, d = warp_full[0, 0], warp_full[0, 1], warp_full[1, 0], warp_full[1, 1]
    rotation = math.degrees(math.atan2(c, a))
    scl = (math.hypot(a, c) + math.hypot(b, d)) / 2.0

    ok, reason = True, ""
    if cc < 0.75:
        ok, reason = False, f"{reason_prefix}; ECC correlation low ({cc:.2f})"
    elif abs(rotation) > cfg.align_max_rotation_deg or abs(scl - 1.0) > cfg.align_max_scale_dev:
        ok, reason = False, f"{reason_prefix}; ECC transform implausible"

    aligned = cv2.warpAffine(fallback, warp_full, (ref_w, ref_h), flags=cv2.INTER_LINEAR)
    return (aligned if ok else fallback), AlignmentMetadata(
        success=ok,
        rotation_deg=round(rotation, 3),
        scale=round(scl, 4),
        translation_px=(round(float(warp_full[0, 2]), 2), round(float(warp_full[1, 2]), 2)),
        inliers=0,
        alignment_error_px=round(float(max(0.0, (1.0 - cc) * 10.0)), 3),
        reason="aligned via ECC fallback" if ok else reason,
    )


def align_to_reference(
    test_bgr: np.ndarray, ref_bgr: np.ndarray, cfg: Settings
) -> tuple[np.ndarray, AlignmentMetadata]:
    """Return (aligned_test_bgr_in_ref_frame, metadata).

    ORB feature matching first; ECC intensity alignment as a fallback. On failure
    the returned image is the test image resized to the reference size (so callers
    never crash) but ``metadata.success`` is ``False`` and the decision engine
    must treat the result as REVIEW / ALIGNMENT_FAILED.
    """
    ref_h, ref_w = ref_bgr.shape[:2]
    fallback = cv2.resize(test_bgr, (ref_w, ref_h), interpolation=cv2.INTER_AREA)

    ref_gray = cv2.cvtColor(ref_bgr, cv2.COLOR_BGR2GRAY)
    test_gray = cv2.cvtColor(test_bgr, cv2.COLOR_BGR2GRAY)

    orb = cv2.ORB_create(nfeatures=cfg.align_orb_features)
    kp_ref, des_ref = orb.detectAndCompute(ref_gray, None)
    kp_test, des_test = orb.detectAndCompute(test_gray, None)

    if des_ref is None or des_test is None or len(kp_ref) < 8 or len(kp_test) < 8:
        return _ecc_align(test_bgr, ref_bgr, cfg, "not enough features detected")

    matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
    raw = matcher.knnMatch(des_test, des_ref, k=2)
    good = [
        m
        for pair in raw
        if len(pair) == 2
        for m, n in [pair]
        if m.distance < cfg.align_lowe_ratio * n.distance
    ]

    if len(good) < cfg.align_min_inliers:
        return _ecc_align(
            test_bgr, ref_bgr, cfg,
            f"only {len(good)} good matches (need {cfg.align_min_inliers})",
        )

    src = np.float32([kp_test[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
    dst = np.float32([kp_ref[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)

    h, mask = cv2.findHomography(
        src, dst, cv2.RANSAC, cfg.align_ransac_reproj_px
    )
    if h is None or mask is None:
        return _ecc_align(test_bgr, ref_bgr, cfg, "homography estimation failed")

    inliers = int(mask.sum())
    if inliers < cfg.align_min_inliers:
        return _ecc_align(test_bgr, ref_bgr, cfg, f"only {inliers} RANSAC inliers")

    # Reprojection error over inliers.
    proj = cv2.perspectiveTransform(src, h)
    err = np.linalg.norm((proj - dst).reshape(-1, 2), axis=1)
    inlier_err = err[mask.ravel().astype(bool)]
    median_err = float(np.median(inlier_err))

    rotation, scale, translation = _decompose(h)

    reason = ""
    ok = True
    if median_err > cfg.align_max_error_px:
        ok, reason = False, f"alignment error {median_err:.1f}px > {cfg.align_max_error_px}px"
    elif abs(rotation) > cfg.align_max_rotation_deg:
        ok, reason = False, f"estimated rotation {rotation:.1f}deg out of range"
    elif abs(scale - 1.0) > cfg.align_max_scale_dev:
        ok, reason = False, f"estimated scale {scale:.2f} out of range"

    aligned = cv2.warpPerspective(
        test_bgr, h, (ref_w, ref_h), flags=cv2.INTER_LINEAR, borderValue=(0, 0, 0)
    )
    orb_ssim = board_ssim(aligned, ref_bgr)

    # Low reprojection error but poor global match => ORB locked onto a wrong
    # (often background-contaminated) homography. Try ECC and keep the better one.
    if ok and orb_ssim < 0.82 and cfg.align_ecc_fallback:
        ecc_img, ecc_meta = _ecc_align(test_bgr, ref_bgr, cfg, "ORB match weak")
        if ecc_meta.success and board_ssim(ecc_img, ref_bgr) > orb_ssim + 0.02:
            return ecc_img, ecc_meta

    if not ok:
        ecc_img, ecc_meta = _ecc_align(test_bgr, ref_bgr, cfg, reason)
        if ecc_meta.success and board_ssim(ecc_img, ref_bgr) > orb_ssim:
            return ecc_img, ecc_meta

    meta = AlignmentMetadata(
        success=ok,
        rotation_deg=round(rotation, 3),
        scale=round(scale, 4),
        translation_px=(round(translation[0], 2), round(translation[1], 2)),
        inliers=inliers,
        alignment_error_px=round(median_err, 3),
        reason=reason,
    )
    return (aligned if ok else fallback), meta
