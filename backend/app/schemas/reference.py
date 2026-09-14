"""Reference board + inspection region definitions."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class ProfileKind(str, Enum):
    PCB = "PCB"
    BOX = "BOX"
    GENERIC = "GENERIC"


class InspectionMode(str, Enum):
    REGIONS = "regions"   # per-component checks (needs regions defined)
    SURFACE = "surface"   # whole-object: does the surface match the reference?


class RegionTolerances(BaseModel):
    """Per-region overrides. Any field left ``None`` falls back to global config."""

    position_tol_px: float | None = None
    rotation_tol_deg: float | None = None
    missing_corr: float | None = None
    ssim_anomaly: float | None = None
    search_margin_px: int | None = None
    # If the component is not expected to have a meaningful orientation
    # (e.g. a round pad), skip the rotation check.
    check_rotation: bool = True


class Region(BaseModel):
    name: str = Field(description="Component / region id, e.g. 'R17', 'CAP1'")
    # Region box in REFERENCE image pixel coords: [x, y, w, h]
    bbox: tuple[int, int, int, int]
    expected_class: str | None = None
    tolerances: RegionTolerances = Field(default_factory=RegionTolerances)

    @property
    def center(self) -> tuple[float, float]:
        x, y, w, h = self.bbox
        return (x + w / 2.0, y + h / 2.0)


class Reference(BaseModel):
    id: str = Field(description="Stable identifier, e.g. 'PCB_MODEL_001'")
    name: str
    kind: ProfileKind = ProfileKind.PCB
    inspection_mode: InspectionMode = InspectionMode.REGIONS
    active: bool = False
    image_path: str
    regions: list[Region] = Field(default_factory=list)
    mm_per_px: float | None = None
    created_at: str
    notes: str = ""


class ReferenceCreate(BaseModel):
    id: str
    name: str
    kind: ProfileKind = ProfileKind.PCB
    inspection_mode: InspectionMode = InspectionMode.REGIONS
    regions: list[Region] = Field(default_factory=list)
    mm_per_px: float | None = None
    notes: str = ""
