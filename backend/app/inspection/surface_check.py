"""Surface inspection mode — whole-object 'does it match the reference?'.

For custom objects where there are no discrete component regions (a printed
carton, a moulded part, a painted surface): capture a clean reference, then a
scratched / dirty / mis-printed / wrong part shows up as a large difference over
the whole surface.

No ORB features are needed (a blank surface has none) — the detected object crop
is resized to the reference and polished with ECC, then compared by SSIM and by
the fraction of the surface that differs strongly.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np
from skimage.metrics import structural_similarity as _ssim

from ..config import Settings


@dataclass
class SurfaceResult:
    ssim: float
    diff_frac: float          # fraction of the surface that differs strongly
    aligned_bgr: np.ndarray
    heatmap: np.ndarray       # uint8 single channel, for visualization


def center_crop(img: np.ndarray, frac: float = 0.6) -> np.ndarray:
    """Central region — used when the object was not detected/cropped, on the
    fixture assumption that it sits roughly in the middle of the frame."""
    h, w = img.shape[:2]
    ch, cw = int(h * frac), int(w * frac)
    y0, x0 = (h - ch) // 2, (w - cw) // 2
    return img[y0 : y0 + ch, x0 : x0 + cw]


def _register(working_bgr: np.ndarray, ref_bgr: np.ndarray) -> np.ndarray:
    """Resize the object crop to the reference, then correct the small placement
    shift with phase correlation (robust on low-texture surfaces) + a bounded ECC
    rotation polish."""
    h, w = ref_bgr.shape[:2]
    out = cv2.resize(working_bgr, (w, h), interpolation=cv2.INTER_AREA)

    ref_g = cv2.GaussianBlur(cv2.cvtColor(ref_bgr, cv2.COLOR_BGR2GRAY), (5, 5), 0).astype(np.float32)

    # 1) translation via phase correlation
    try:
        cur = cv2.GaussianBlur(cv2.cvtColor(out, cv2.COLOR_BGR2GRAY), (5, 5), 0).astype(np.float32)
        (dx, dy), resp = cv2.phaseCorrelate(ref_g, cur)
        if resp > 0.05 and abs(dx) < 0.25 * w and abs(dy) < 0.25 * h:
            M = np.float32([[1, 0, -dx], [0, 1, -dy]])
            out = cv2.warpAffine(out, M, (w, h), flags=cv2.INTER_LINEAR,
                                 borderMode=cv2.BORDER_REPLICATE)
    except cv2.error:
        pass

    # 2) small rotation/scale via ECC (downscaled), only trust a sane result
    try:
        s = 320.0 / max(h, w)
        small = lambda im: cv2.resize(cv2.cvtColor(im, cv2.COLOR_BGR2GRAY), None, fx=s, fy=s).astype(np.float32)  # noqa: E731
        warp = np.eye(2, 3, dtype=np.float32)
        crit = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 50, 1e-4)
        cc, warp = cv2.findTransformECC(small(ref_bgr), small(out), warp, cv2.MOTION_EUCLIDEAN, crit, None, 5)
        warp[:, 2] /= s
        rot = abs(np.degrees(np.arctan2(warp[1, 0], warp[0, 0])))
        if cc > 0.5 and rot < 12 and abs(warp[0, 2]) < 0.1 * w and abs(warp[1, 2]) < 0.1 * h:
            out = cv2.warpAffine(out, warp, (w, h), flags=cv2.INTER_LINEAR,
                                 borderMode=cv2.BORDER_REPLICATE)
    except cv2.error:
        pass

    return out


def inspect_surface(
    working_bgr: np.ndarray, ref_bgr: np.ndarray, cfg: Settings
) -> SurfaceResult:
    aligned = _register(working_bgr, ref_bgr)

    a = cv2.GaussianBlur(cv2.cvtColor(aligned, cv2.COLOR_BGR2GRAY), (5, 5), 0)
    b = cv2.GaussianBlur(cv2.cvtColor(ref_bgr, cv2.COLOR_BGR2GRAY), (5, 5), 0)

    diff = cv2.absdiff(a, b)
    strong = diff > cfg.surface_diff_threshold
    # ignore a thin border (warp edges / crop slop)
    m = max(4, int(0.03 * min(a.shape)))
    strong[:m, :] = strong[-m:, :] = strong[:, :m] = strong[:, -m:] = False
    diff_frac = float(strong.mean())

    try:
        ssim_val = float(_ssim(a, b))
    except ValueError:
        ssim_val = 0.0

    heat = cv2.normalize(diff, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    return SurfaceResult(round(ssim_val, 4), round(diff_frac, 4), aligned, heat)
