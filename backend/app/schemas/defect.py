"""Defect types and the per-defect record."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class DefectType(str, Enum):
    MISSING_COMPONENT = "MISSING_COMPONENT"
    SHIFTED_COMPONENT = "SHIFTED_COMPONENT"
    ROTATED_COMPONENT = "ROTATED_COMPONENT"
    SIZE_DEVIATION = "SIZE_DEVIATION"
    VISUAL_ANOMALY = "VISUAL_ANOMALY"
    WRONG_COMPONENT = "WRONG_COMPONENT"        # detected class != expected class (YOLO)
    UNEXPECTED_COMPONENT = "UNEXPECTED_COMPONENT"  # component where none is expected (YOLO)


# Defects that force a DEFECTIVE verdict when confirmed beyond tolerance.
CRITICAL_DEFECTS: frozenset[DefectType] = frozenset(
    {
        DefectType.MISSING_COMPONENT,
        DefectType.SHIFTED_COMPONENT,
        DefectType.ROTATED_COMPONENT,
        DefectType.WRONG_COMPONENT,
    }
)


class Defect(BaseModel):
    component: str = Field(description="Region / component identifier, e.g. 'R17'")
    type: DefectType
    confidence: float = Field(ge=0.0, le=1.0)

    # What / where / why -----------------------------------------------------
    expected: str = ""
    observed: str = ""
    expected_position: tuple[float, float] | None = None
    actual_position: tuple[float, float] | None = None
    deviation_px: float | None = None
    deviation_mm: float | None = None
    allowed_px: float | None = None
    rotation_deg: float | None = None
    allowed_rotation_deg: float | None = None

    # Axis-aligned box in aligned-image pixel coords: [x1, y1, x2, y2]
    bbox: tuple[int, int, int, int] | None = None
