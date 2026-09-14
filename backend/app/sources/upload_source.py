"""Decode an image from raw bytes (an HTTP file upload)."""

from __future__ import annotations

import cv2
import numpy as np

from .base import ImageSource, SourceError


class UploadSource(ImageSource):
    def __init__(self, data: bytes, filename: str = "upload") -> None:
        self._data = data
        self.filename = filename

    def read(self) -> np.ndarray:
        if not self._data:
            raise SourceError("Empty upload payload")
        buf = np.frombuffer(self._data, dtype=np.uint8)
        img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
        if img is None:
            raise SourceError(
                f"Could not decode uploaded file '{self.filename}' as an image"
            )
        return img
