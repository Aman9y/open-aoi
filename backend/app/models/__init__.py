from __future__ import annotations

from ..config import Settings
from ..logging_config import get_logger
from .anomaly_detector import AnomalyDetector, NullAnomalyDetector
from .component_detector import (
    MODEL_NOT_CONFIGURED,
    ComponentDetector,
    Detection,
    NullComponentDetector,
)

log = get_logger(__name__)

__all__ = [
    "ComponentDetector",
    "Detection",
    "NullComponentDetector",
    "AnomalyDetector",
    "NullAnomalyDetector",
    "MODEL_NOT_CONFIGURED",
    "build_component_detector",
]

# Cache the detector so the model file is loaded once, not per request.
_CACHE: dict[str, ComponentDetector] = {}


def build_component_detector(cfg: Settings) -> ComponentDetector:
    """Return a ready YOLO detector if a model file is configured and loads,
    otherwise a null detector that reports ``MODEL NOT CONFIGURED``."""
    key = str(cfg.yolo_model_path or "")
    if key in _CACHE:
        return _CACHE[key]

    if not cfg.yolo_model_path:
        det: ComponentDetector = NullComponentDetector()
    else:
        from .yolo_detector import YOLOComponentDetector

        det = YOLOComponentDetector(
            cfg.yolo_model_path, cfg.yolo_confidence, cfg.yolo_class_aliases
        )
    _CACHE[key] = det
    return det


def reset_detector_cache() -> None:
    _CACHE.clear()
