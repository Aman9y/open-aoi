"""Stage A/B — decode sanity, resize, grayscale, image-quality gate."""

from __future__ import annotations

import cv2
import numpy as np

from ..config import Settings
from ..schemas.inspection import QualityReport


def resize_max(img: np.ndarray, max_dim: int) -> np.ndarray:
    """Downscale so the longest side == ``max_dim`` (never upscales)."""
    h, w = img.shape[:2]
    longest = max(h, w)
    if longest <= max_dim:
        return img
    scale = max_dim / float(longest)
    return cv2.resize(
        img, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA
    )


def to_gray(img: np.ndarray) -> np.ndarray:
    if img.ndim == 2:
        return img
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def is_probably_valid_image(img: np.ndarray | None) -> bool:
    """Cheap sanity check for stage A (no detector yet)."""
    if img is None or img.size == 0:
        return False
    h, w = img.shape[:2]
    if h < 64 or w < 64:
        return False
    # A frame that is almost entirely one value is not a board.
    if float(to_gray(img).std()) < 3.0:
        return False
    return True


def quality_check(img: np.ndarray, cfg: Settings) -> QualityReport:
    """Stage B — blur / exposure / contrast gate."""
    gray = to_gray(img)
    blur = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    brightness = float(gray.mean())
    contrast = float(gray.std())
    overexposed = float(np.mean(gray >= 250))

    issues: list[str] = []
    if blur < cfg.quality_blur_min:
        issues.append(f"image is blurred (sharpness {blur:.0f} < {cfg.quality_blur_min:.0f})")
    if brightness < cfg.quality_brightness_min:
        issues.append(f"image too dark (brightness {brightness:.0f})")
    if brightness > cfg.quality_brightness_max:
        issues.append(f"image too bright (brightness {brightness:.0f})")
    if contrast < cfg.quality_contrast_min:
        issues.append(f"insufficient contrast (std {contrast:.0f})")
    if overexposed > cfg.quality_overexposed_max_frac:
        issues.append(f"overexposed ({overexposed * 100:.0f}% of pixels clipped)")

    return QualityReport(
        passed=not issues,
        blur_score=round(blur, 2),
        brightness=round(brightness, 2),
        contrast=round(contrast, 2),
        overexposed_frac=round(overexposed, 4),
        issues=issues,
    )
