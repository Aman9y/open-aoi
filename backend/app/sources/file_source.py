"""Read an image from a path on disk."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from .base import ImageSource, SourceError


class FileSource(ImageSource):
    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    def read(self) -> np.ndarray:
        if not self._path.is_file():
            raise SourceError(f"Image file not found: {self._path}")
        # imread handles unicode paths poorly on Windows; decode from bytes.
        data = np.fromfile(str(self._path), dtype=np.uint8)
        img = cv2.imdecode(data, cv2.IMREAD_COLOR)
        if img is None:
            raise SourceError(f"Could not decode image: {self._path}")
        return img
