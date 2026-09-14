"""ComponentDetector interface (optional ML — disabled by default).

Milestone 1 uses only the deterministic reference pipeline. When a trained model
is added (milestone 3) it plugs in here. Until then the null implementation
reports ``MODEL NOT CONFIGURED`` and the pipeline never pretends inference ran.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass

import numpy as np

MODEL_NOT_CONFIGURED = "MODEL NOT CONFIGURED"


@dataclass
class Detection:
    label: str
    confidence: float
    bbox: tuple[int, int, int, int]  # x1, y1, x2, y2 in aligned-image coords


class ComponentDetector(abc.ABC):
    @property
    @abc.abstractmethod
    def status(self) -> str:
        """``"READY"`` or ``MODEL_NOT_CONFIGURED``."""

    @abc.abstractmethod
    def detect(self, image_bgr: np.ndarray) -> list[Detection]:
        ...


class NullComponentDetector(ComponentDetector):
    @property
    def status(self) -> str:
        return MODEL_NOT_CONFIGURED

    def detect(self, image_bgr: np.ndarray) -> list[Detection]:
        return []
