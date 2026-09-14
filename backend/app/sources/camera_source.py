"""Live camera / phone-IP-camera sources.

Not on the milestone-1 critical path (upload works without any hardware), but the
implementation is here so the engine stays decoupled from capture.

Phone-as-webcam: run an IP-webcam app on the phone and pass its stream URL, e.g.
``StreamSource("http://192.168.1.42:8080/video")``. USB tether is more stable than
Wi-Fi for a demo.
"""

from __future__ import annotations

import sys
import time

import cv2
import numpy as np

from ..logging_config import get_logger
from .base import ImageSource, SourceError

log = get_logger(__name__)

# DirectShow avoids a noisy MSMF depth-camera probe on Windows.
_LOCAL_BACKEND = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY


class CameraSource(ImageSource):
    """Local capture device (USB webcam, or a phone exposed as a webcam)."""

    def __init__(self, index: int = 0, warmup_frames: int = 5) -> None:
        self._cap = cv2.VideoCapture(index, _LOCAL_BACKEND)
        if not self._cap.isOpened():
            raise SourceError(f"Could not open camera index {index}")
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        for _ in range(max(0, warmup_frames)):
            self._cap.read()
            time.sleep(0.02)

    def read(self) -> np.ndarray:
        ok, frame = self._cap.read()
        if not ok or frame is None:
            raise SourceError("Camera returned no frame")
        return frame

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None


class StreamSource(ImageSource):
    """Network video stream (phone IP camera, RTSP, MJPEG)."""

    def __init__(self, url: str, open_timeout_s: float = 8.0) -> None:
        self._url = url
        self._cap = cv2.VideoCapture(url)
        deadline = time.monotonic() + open_timeout_s
        while not self._cap.isOpened() and time.monotonic() < deadline:
            time.sleep(0.2)
        if not self._cap.isOpened():
            raise SourceError(f"Could not open stream: {url}")

    def read(self) -> np.ndarray:
        ok, frame = self._cap.read()
        if not ok or frame is None:
            raise SourceError(f"Stream returned no frame: {self._url}")
        return frame

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None
