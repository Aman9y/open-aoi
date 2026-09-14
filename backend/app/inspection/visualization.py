"""Annotated result image: region boxes, defect labels, optional diff heatmap."""

from __future__ import annotations

import cv2
import numpy as np

from ..schemas.defect import Defect, DefectType
from ..schemas.inspection import ComponentDetection, InspectionStatus, RegionMeasurement

_GREEN = (80, 200, 80)
_RED = (60, 60, 220)
_AMBER = (40, 170, 240)
_GREY = (150, 150, 150)

_STATUS_COLOR = {
    InspectionStatus.GOOD: _GREEN,
    InspectionStatus.DEFECTIVE: _RED,
    InspectionStatus.REVIEW: _AMBER,
}

_DEFECT_LABEL = {
    DefectType.MISSING_COMPONENT: "MISSING",
    DefectType.SHIFTED_COMPONENT: "SHIFTED",
    DefectType.ROTATED_COMPONENT: "ROTATED",
    DefectType.SIZE_DEVIATION: "SIZE",
    DefectType.VISUAL_ANOMALY: "ANOMALY",
}


def _text(img: np.ndarray, s: str, org: tuple[int, int], color, scale: float = 0.5) -> None:
    cv2.putText(img, s, org, cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), 3, cv2.LINE_AA)
    cv2.putText(img, s, org, cv2.FONT_HERSHEY_SIMPLEX, scale, color, 1, cv2.LINE_AA)


_CYAN = (200, 200, 60)


def annotate(
    aligned_bgr: np.ndarray,
    status: InspectionStatus,
    measurements: list[RegionMeasurement],
    defects: list[Defect],
    heatmap: np.ndarray | None = None,
    detections: list[ComponentDetection] | None = None,
) -> np.ndarray:
    out = aligned_bgr.copy()

    if heatmap is not None and status != InspectionStatus.GOOD:
        color = cv2.applyColorMap(heatmap, cv2.COLORMAP_JET)
        mask = (heatmap > 60).astype(np.uint8)[:, :, None]
        out = np.where(mask == 1, cv2.addWeighted(out, 0.55, color, 0.45, 0), out)

    # Object-detector boxes (dashed-ish, distinct colour) under the region marks.
    for d in detections or []:
        x1, y1, x2, y2 = d.bbox
        cv2.rectangle(out, (x1, y1), (x2, y2), _CYAN, 1)
        _text(out, f"{d.label} {d.confidence*100:.0f}%", (x1, max(10, y1 - 4)), _CYAN, 0.4)

    defect_regions = {d.component for d in defects}

    for m in measurements:
        x, y, w, h = m.bbox
        col = _GREY if not m.found else (_RED if m.name in defect_regions else _GREEN)
        cv2.rectangle(out, (x, y), (x + w, y + h), col, 2)
        _text(out, m.name, (x, max(12, y - 6)), col, 0.45)

    for i, d in enumerate(defects):
        if d.bbox:
            x1, y1, x2, y2 = d.bbox
            cv2.rectangle(out, (x1, y1), (x2, y2), _RED, 2)
            label = f"{d.component}: {_DEFECT_LABEL.get(d.type, d.type.value)} {d.confidence*100:.0f}%"
            _text(out, label, (x1, min(out.shape[0] - 6, y2 + 16)), _RED, 0.45)

    # Status banner
    banner_h = 34
    strip = out[:banner_h].copy()
    strip[:] = _STATUS_COLOR[status]
    out[:banner_h] = cv2.addWeighted(out[:banner_h], 0.25, strip, 0.75, 0)
    _text(out, status.value, (10, 24), (255, 255, 255), 0.8)

    return out


def montage(images: list[np.ndarray], labels: list[str], row_height: int = 360) -> np.ndarray:
    """original | cropped | aligned | annotated in one labelled strip."""
    tiles = []
    for im, lab in zip(images, labels):
        if im is None or im.size == 0:
            im = np.zeros((row_height, row_height, 3), np.uint8)
        scale = row_height / im.shape[0]
        r = cv2.resize(im, (max(1, int(im.shape[1] * scale)), row_height))
        cv2.rectangle(r, (0, 0), (r.shape[1] - 1, 22), (0, 0, 0), -1)
        _text(r, lab, (8, 16), (255, 255, 255), 0.5)
        tiles.append(r)
        tiles.append(np.full((row_height, 3, 3), 40, np.uint8))  # divider
    return cv2.hconcat(tiles[:-1])
