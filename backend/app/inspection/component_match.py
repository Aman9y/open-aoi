"""Fuse object-detector (YOLO) hits with the deterministic region results.

Design stance (see ARCHITECTURE §3): YOLO **adds** information, it does not
override the deterministic verdict.

  * class mismatch at an expected location -> WRONG_COMPONENT defect (critical)
  * detector agrees / disagrees with the template-match "present" call ->
    recorded on the RegionMeasurement as corroboration (surfaced in the UI,
    used only to nudge confidence, never to flip GOOD/DEFECTIVE by itself)
  * stray detection far from any region -> UNEXPECTED_COMPONENT, opt-in
    (``AOI_YOLO_FLAG_UNEXPECTED``), REVIEW-only severity in practice
"""

from __future__ import annotations

from ..config import Settings
from ..models.component_detector import Detection
from ..schemas.defect import Defect, DefectType
from ..schemas.inspection import ComponentDetection, RegionMeasurement
from ..schemas.reference import Region


def _iou_or_containment(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
    inter = iw * ih
    if inter == 0:
        return 0.0
    area_a = max(1, (ax2 - ax1) * (ay2 - ay1))
    area_b = max(1, (bx2 - bx1) * (by2 - by1))
    # max of IoU and "fraction of the smaller box covered" — tolerant of the
    # detector drawing a tighter/looser box than the region.
    return max(inter / (area_a + area_b - inter), inter / min(area_a, area_b))


def _region_xyxy(r: Region) -> tuple[int, int, int, int]:
    x, y, w, h = r.bbox
    return (x, y, x + w, y + h)


def fuse(
    regions: list[Region],
    measurements: list[RegionMeasurement],
    detections: list[Detection],
    cfg: Settings,
) -> tuple[list[RegionMeasurement], list[Defect], list[ComponentDetection]]:
    by_name = {m.name: m for m in measurements}
    used: set[int] = set()
    defects: list[Defect] = []
    out_dets: list[ComponentDetection] = []

    for region in regions:
        m = by_name.get(region.name)
        if m is None:
            continue
        rbox = _region_xyxy(region)

        best_i, best_score = -1, cfg.yolo_match_iou
        for i, det in enumerate(detections):
            score = _iou_or_containment(rbox, det.bbox)
            if score > best_score:
                best_i, best_score = i, score

        if best_i < 0:
            m.detector_agreement = "absent" if m.found else "agree"
            continue

        det = detections[best_i]
        used.add(best_i)
        m.detector_class = det.label
        m.detector_confidence = round(det.confidence, 3)

        expected = (region.expected_class or "").lower().strip()
        class_known = bool(expected) and bool(det.label)
        class_conflict = class_known and det.label != expected

        if class_conflict:
            m.detector_agreement = "conflict"
            defects.append(
                Defect(
                    component=region.name,
                    type=DefectType.WRONG_COMPONENT,
                    confidence=round(min(0.97, 0.55 + 0.4 * det.confidence), 3),
                    expected=f"Component of class '{expected}'",
                    observed=f"Detector identifies a '{det.label}' "
                    f"({det.confidence * 100:.0f}% conf) at this location",
                    expected_position=m.expected_center,
                    actual_position=m.observed_center,
                    bbox=det.bbox,
                )
            )
        elif not m.found:
            # template match said MISSING but the detector sees something here
            m.detector_agreement = "conflict"
        else:
            m.detector_agreement = "agree"

        out_dets.append(
            ComponentDetection(
                label=det.label, confidence=round(det.confidence, 3),
                bbox=det.bbox, matched_region=region.name,
            )
        )

    for i, det in enumerate(detections):
        if i in used:
            continue
        cd = ComponentDetection(
            label=det.label, confidence=round(det.confidence, 3), bbox=det.bbox
        )
        out_dets.append(cd)
        if cfg.yolo_flag_unexpected and det.confidence >= max(0.5, cfg.yolo_confidence + 0.15):
            defects.append(
                Defect(
                    component=f"@{det.bbox[0]},{det.bbox[1]}",
                    type=DefectType.UNEXPECTED_COMPONENT,
                    confidence=round(det.confidence, 3),
                    expected="No component defined at this location",
                    observed=f"Detector found a '{det.label}' ({det.confidence * 100:.0f}% conf)",
                    bbox=det.bbox,
                )
            )

    return measurements, defects, out_dets
