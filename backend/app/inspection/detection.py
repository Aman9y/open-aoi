"""Stage A (part 2) — locate the board in a real photo and rectify it.

Real camera images put the board somewhere inside a larger, cluttered frame,
often at a slight angle. This module finds the largest board-like quadrilateral,
perspective-corrects it, and hands a tight crop to the alignment stage. If the
board already fills the frame (a tight fixture) or nothing board-like is found,
it passes the image through unchanged and says so.

Fully deterministic OpenCV. No ML.
"""

from __future__ import annotations

import cv2
import numpy as np

from ..config import Settings
from ..logging_config import get_logger
from ..schemas.inspection import BoardDetection

log = get_logger(__name__)


def _order_corners(pts: np.ndarray) -> np.ndarray:
    """Return corners ordered tl, tr, br, bl."""
    pts = pts.reshape(4, 2).astype(np.float32)
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1).ravel()
    return np.array(
        [pts[np.argmin(s)], pts[np.argmin(d)], pts[np.argmax(s)], pts[np.argmax(d)]],
        dtype=np.float32,
    )


def _rectify(image: np.ndarray, quad: np.ndarray, pad_frac: float) -> np.ndarray:
    tl, tr, br, bl = quad
    w = max(np.linalg.norm(br - bl), np.linalg.norm(tr - tl))
    h = max(np.linalg.norm(tr - br), np.linalg.norm(tl - bl))
    w, h = int(round(w)), int(round(h))
    if w < 32 or h < 32:
        return image
    pad = int(round(pad_frac * max(w, h)))
    dst = np.array(
        [[pad, pad], [w + pad, pad], [w + pad, h + pad], [pad, h + pad]],
        dtype=np.float32,
    )
    m = cv2.getPerspectiveTransform(quad, dst)
    return cv2.warpPerspective(image, m, (w + 2 * pad, h + 2 * pad), flags=cv2.INTER_LINEAR)


def _largest_quad(gray: np.ndarray, min_area: float, sigma: float) -> np.ndarray | None:
    blurred = cv2.bilateralFilter(gray, 7, 60, 60)
    med = float(np.median(blurred))
    lo = int(max(0, (1.0 - sigma) * med))
    hi = int(min(255, (1.0 + sigma) * med))
    edges = cv2.Canny(blurred, lo, hi)
    edges = cv2.dilate(edges, np.ones((5, 5), np.uint8), iterations=2)
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, np.ones((13, 13), np.uint8))

    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best_quad: np.ndarray | None = None
    best_quad_area = min_area
    best_rect: np.ndarray | None = None
    best_rect_score = 0.0

    for c in contours:
        area = cv2.contourArea(c)
        if area < min_area:
            continue
        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.02 * peri, True)
        if len(approx) == 4 and cv2.isContourConvex(approx) and area >= best_quad_area:
            best_quad, best_quad_area = approx, area
        # Fallback: the biggest blob that is *mostly* a rectangle (rectangularity =
        # contour area / its min-area-rect area). Handles low-contrast edges where
        # approxPolyDP breaks the outline into 5-8 points.
        rect = cv2.minAreaRect(c)
        rect_area = max(1.0, rect[1][0] * rect[1][1])
        rectangularity = area / rect_area
        if rectangularity > 0.82 and area > best_rect_score:
            best_rect = cv2.boxPoints(rect).astype(np.float32)
            best_rect_score = area

    if best_quad is not None:
        return best_quad
    return best_rect


def _color_fallback(bgr: np.ndarray, min_area: float) -> np.ndarray | None:
    """Largest saturated blob (a coloured board against a neutral background)."""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    sat = hsv[:, :, 1]
    _, mask = cv2.threshold(sat, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((7, 7), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    c = max(contours, key=cv2.contourArea)
    if cv2.contourArea(c) < min_area:
        return None
    box = cv2.boxPoints(cv2.minAreaRect(c))
    return box.astype(np.float32)


def object_bbox(
    image_bgr: np.ndarray, min_area_frac: float = 0.04, max_area_frac: float = 0.92
) -> tuple[int, int, int, int] | None:
    """Bounding box of the object the operator placed in the frame.

    Surface mode assumes a fixture: the part sits roughly in the middle. This
    finds clusters of edges/texture and picks the one that is both sizeable and
    near the centre (so a cluttered edge — keyboard, cable — doesn't win).
    Returns (x, y, w, h) or None.
    """
    h, w = image_bgr.shape[:2]
    fcx, fcy = w / 2, h / 2
    gray = cv2.bilateralFilter(cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY), 7, 50, 50)
    med = float(np.median(gray))
    edges = cv2.Canny(gray, int(max(0, 0.66 * med)), int(min(255, 1.33 * med)))
    edges = cv2.dilate(edges, np.ones((11, 11), np.uint8), iterations=2)
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, np.ones((21, 21), np.uint8))

    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best, best_score = None, 0.0
    for c in contours:
        x, y, bw, bh = cv2.boundingRect(c)
        area = bw * bh
        if area < min_area_frac * h * w or area > max_area_frac * h * w:
            continue
        # background clutter (keyboard, cable, desk edge) enters from the frame
        # border; the operator's part sits inside. Penalise border contact hard.
        touch = (x <= 2) + (y <= 2) + (x + bw >= w - 2) + (y + bh >= h - 2)
        if touch >= 2:
            continue
        cx, cy = x + bw / 2, y + bh / 2
        dist = np.hypot((cx - fcx) / w, (cy - fcy) / h)   # 0 = centred
        score = (area / (h * w)) * max(0.02, 1.0 - 2.6 * dist) * (0.5 if touch else 1.0)
        if score > best_score:
            best, best_score = (x, y, bw, bh), score

    if best is None:
        return None
    x, y, bw, bh = best
    pad = int(0.05 * max(bw, bh))
    x0, y0 = max(0, x - pad), max(0, y - pad)
    x1, y1 = min(w, x + bw + pad), min(h, y + bh + pad)
    return (x0, y0, x1 - x0, y1 - y0)


def detect_board(
    image_bgr: np.ndarray, cfg: Settings, reference_aspect: float | None = None
) -> tuple[np.ndarray, BoardDetection]:
    """Return (working_image, detection). ``working_image`` is the rectified crop
    when a board is found, otherwise the input unchanged."""
    h, w = image_bgr.shape[:2]
    frame_area = float(h * w)
    min_area = cfg.detect_min_area_frac * frame_area

    if not cfg.detect_enabled:
        return image_bgr, BoardDetection(found=False, method="none", note="detection disabled")

    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)

    quad = _largest_quad(gray, min_area, cfg.detect_canny_sigma)
    method = "quad"
    if quad is None:
        box = _color_fallback(image_bgr, min_area)
        quad, method = (box, "color") if box is not None else (None, "none")

    if quad is None:
        return image_bgr, BoardDetection(
            found=False, method="none", coverage=0.0,
            note="no board-like region found; using full frame",
        )

    ordered = _order_corners(quad)
    coverage = float(cv2.contourArea(ordered.astype(np.float32))) / frame_area

    if coverage >= cfg.detect_max_area_frac:
        return image_bgr, BoardDetection(
            found=False, method="none", coverage=round(coverage, 3),
            note="board already fills the frame; no crop needed",
        )

    # Aspect-ratio sanity vs the reference, if we know it.
    if reference_aspect:
        ew = max(np.linalg.norm(ordered[1] - ordered[0]), np.linalg.norm(ordered[2] - ordered[3]))
        eh = max(np.linalg.norm(ordered[3] - ordered[0]), np.linalg.norm(ordered[2] - ordered[1]))
        aspect = ew / eh if eh else 0.0
        rel = abs(aspect - reference_aspect) / reference_aspect
        if rel > cfg.detect_aspect_tolerance:
            return image_bgr, BoardDetection(
                found=False, method=method, coverage=round(coverage, 3),
                note=f"detected quad aspect {aspect:.2f} unlike reference {reference_aspect:.2f}; "
                "using full frame",
            )

    cropped = _rectify(image_bgr, ordered, cfg.detect_pad_frac)
    log.info("board detected via %s, coverage %.2f", method, coverage)
    return cropped, BoardDetection(
        found=True, method=method, coverage=round(coverage, 3),
        quad=[(round(float(x), 1), round(float(y), 1)) for x, y in ordered],
    )
