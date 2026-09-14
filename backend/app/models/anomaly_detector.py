"""AnomalyDetector interface — extension point for PatchCore / EfficientAD.

Not implemented in milestone 1. The deterministic reference comparison in
:mod:`app.inspection.reference_checker` covers stage F for now.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass

import numpy as np

MODEL_NOT_CONFIGURED = "MODEL NOT CONFIGURED"


@dataclass
class AnomalyMap:
    score: float                 # image-level anomaly score
    heatmap: np.ndarray | None   # per-pixel anomaly, same HxW as input


class AnomalyDetector(abc.ABC):
    @property
    @abc.abstractmethod
    def status(self) -> str:
        ...

    @abc.abstractmethod
    def score(self, image_bgr: np.ndarray) -> AnomalyMap:
        ...


class NullAnomalyDetector(AnomalyDetector):
    @property
    def status(self) -> str:
        return MODEL_NOT_CONFIGURED

    def score(self, image_bgr: np.ndarray) -> AnomalyMap:
        return AnomalyMap(score=0.0, heatmap=None)
