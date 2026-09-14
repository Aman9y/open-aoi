"""InspectionProfile — what the generic engine operates on.

A profile is *data*: a known-good reference image plus a list of inspection
regions with tolerances. The engine never branches on ``kind``; product-specific
behaviour is expressed entirely through region config. Adding a new product
(e.g. a printed box) = adding a new reference + regions, no engine changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from ..schemas.reference import InspectionMode, ProfileKind, Reference, Region


@dataclass
class InspectionProfile:
    reference: Reference
    reference_dir: Path

    @property
    def id(self) -> str:
        return self.reference.id

    @property
    def kind(self) -> ProfileKind:
        return self.reference.kind

    @property
    def regions(self) -> list[Region]:
        return self.reference.regions

    @property
    def inspection_mode(self) -> InspectionMode:
        return self.reference.inspection_mode

    @property
    def mm_per_px(self) -> float:
        return self.reference.mm_per_px or 0.0

    def load_reference_image(self) -> np.ndarray:
        path = self.reference_dir / "reference.png"
        data = np.fromfile(str(path), dtype=np.uint8)
        img = cv2.imdecode(data, cv2.IMREAD_COLOR)
        if img is None:
            raise FileNotFoundError(f"Reference image missing/corrupt: {path}")
        return img
