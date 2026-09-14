"""Inspection result contract (API-facing)."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from .defect import Defect


class InspectionStatus(str, Enum):
    GOOD = "GOOD"
    DEFECTIVE = "DEFECTIVE"
    REVIEW = "REVIEW"


class ModelStatus(str, Enum):
    DETERMINISTIC_ONLY = "DETERMINISTIC_ONLY"      # no detector requested
    MODEL_NOT_CONFIGURED = "MODEL NOT CONFIGURED"  # requested but unavailable
    YOLO_ACTIVE = "YOLO_ACTIVE"                    # detector ran and contributed


class ReasonCode(str, Enum):
    OK = "OK"
    INVALID_IMAGE = "INVALID_IMAGE"
    POOR_IMAGE_QUALITY = "POOR_IMAGE_QUALITY"
    ALIGNMENT_FAILED = "ALIGNMENT_FAILED"
    CRITICAL_DEFECT = "CRITICAL_DEFECT"
    VISUAL_ANOMALY = "VISUAL_ANOMALY"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    CONTRADICTORY = "CONTRADICTORY"


class QualityReport(BaseModel):
    passed: bool
    blur_score: float          # variance of Laplacian (higher = sharper)
    brightness: float          # mean grey level
    contrast: float            # std dev of grey levels
    overexposed_frac: float
    issues: list[str] = Field(default_factory=list)


class BoardDetection(BaseModel):
    found: bool
    method: str = "none"                       # quad | min_area_rect | color | none
    coverage: float = 0.0                       # fraction of the frame the board covers
    quad: list[tuple[float, float]] = Field(default_factory=list)  # 4 corners, tl-tr-br-bl
    note: str = ""


class AlignmentMetadata(BaseModel):
    success: bool
    rotation_deg: float = 0.0
    scale: float = 1.0
    translation_px: tuple[float, float] = (0.0, 0.0)
    inliers: int = 0
    alignment_error_px: float = 0.0
    reason: str = ""


class ComponentDetection(BaseModel):
    """A single object-detector (YOLO) hit, in aligned-image pixel coords."""

    label: str
    confidence: float
    bbox: tuple[int, int, int, int]  # x1, y1, x2, y2
    matched_region: str | None = None


class RegionMeasurement(BaseModel):
    """Raw per-region measurement — useful for the UI 'why' panel and debugging."""

    name: str
    found: bool
    peak_corr: float
    offset_px: float
    rotation_deg: float
    ssim: float
    color_delta: float = 0.0  # CIELAB distance of mean region colour vs reference
    expected_center: tuple[float, float]
    observed_center: tuple[float, float] | None = None
    bbox: tuple[int, int, int, int]
    # Object-detector corroboration (only set when a YOLO model is configured):
    detector_class: str | None = None      # class the detector saw at this region
    detector_confidence: float | None = None
    detector_agreement: str | None = None  # "agree" | "conflict" | "absent" | None


class InspectionResult(BaseModel):
    result_type: str = "single"
    inspection_id: str
    timestamp: str
    reference_id: str
    profile_kind: str

    status: InspectionStatus
    reason: ReasonCode
    explanation: str = ""
    overall_confidence: float = Field(ge=0.0, le=1.0)
    inspection_time_ms: int

    quality: QualityReport
    detection: BoardDetection = Field(default_factory=lambda: BoardDetection(found=False))
    alignment: AlignmentMetadata
    board_similarity: float = 0.0  # whole-board SSIM of aligned vs reference (0-1)
    regions: list[RegionMeasurement] = Field(default_factory=list)
    detections: list[ComponentDetection] = Field(default_factory=list)
    defects: list[Defect] = Field(default_factory=list)

    # Media (URLs relative to the API host)
    original_image_path: str = ""
    cropped_image_path: str = ""
    aligned_image_path: str = ""
    annotated_image_path: str = ""
    montage_image_path: str = ""

    model_status: ModelStatus = ModelStatus.DETERMINISTIC_ONLY


class ViewResult(BaseModel):
    name: str                 # e.g. "front", "top", "cam-2"
    source: str = ""          # camera index / stream URL it came from
    result: InspectionResult


class MultiViewResult(BaseModel):
    """Combined verdict from inspecting one object with several cameras at once."""

    result_type: str = "multi"
    inspection_id: str
    timestamp: str
    reference_id: str          # comma-joined view references (for the history row)
    profile_kind: str = "MULTI"

    status: InspectionStatus   # worst of the per-view statuses
    reason: ReasonCode
    explanation: str = ""
    overall_confidence: float = Field(ge=0.0, le=1.0)
    inspection_time_ms: int

    view_count: int
    defects: list[Defect] = Field(default_factory=list)  # union, component prefixed with view
    views: list[ViewResult] = Field(default_factory=list)
    montage_image_path: str = ""
    model_status: ModelStatus = ModelStatus.DETERMINISTIC_ONLY
