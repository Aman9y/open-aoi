"""Image input abstraction.

The inspection engine only ever receives a decoded BGR ``numpy`` array. How that
array is obtained (disk, HTTP upload, USB webcam, phone IP camera) is the concern
of an :class:`ImageSource` implementation and nothing else.
"""

from __future__ import annotations

import abc

import numpy as np


class SourceError(RuntimeError):
    """Raised when an image cannot be obtained or decoded."""


class ImageSource(abc.ABC):
    """Yields BGR uint8 frames of shape (H, W, 3)."""

    @abc.abstractmethod
    def read(self) -> np.ndarray:
        """Return a single frame. Raise :class:`SourceError` on failure."""

    def close(self) -> None:  # pragma: no cover - optional for stateless sources
        """Release any held resources."""

    def __enter__(self) -> "ImageSource":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
