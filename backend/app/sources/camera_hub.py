"""Shared, lazily-started capture feeds.

A single OpenCV capture per *source* (a local device index or a stream URL) is
read by a background thread; both the MJPEG preview endpoint and the "capture &
inspect" snapshot pull the latest frame from it. Feeds that nobody has touched
for a short while are released automatically.

This keeps a USB webcam (single-consumer) usable for preview + snapshot at the
same time, and avoids opening/closing the device on every request.
"""

from __future__ import annotations

import threading
import time

import cv2
import numpy as np

from ..logging_config import get_logger
from .base import SourceError
from .camera_source import _LOCAL_BACKEND

log = get_logger(__name__)

_IDLE_TIMEOUT_S = 20.0
_OPEN_TIMEOUT_S = 8.0


def _open(source: str) -> cv2.VideoCapture:
    if source.isdigit():
        cap = cv2.VideoCapture(int(source), _LOCAL_BACKEND)
        # Ask for 720p — the default 640x480 is too soft for small components.
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        return cap
    return cv2.VideoCapture(source)


class _Feed:
    def __init__(self, source: str) -> None:
        self.source = source
        self._cap = _open(source)
        # A local device index either opens or it doesn't; only network streams
        # are worth waiting on.
        if not source.isdigit():
            deadline = time.monotonic() + _OPEN_TIMEOUT_S
            while not self._cap.isOpened() and time.monotonic() < deadline:
                time.sleep(0.2)
        if not self._cap.isOpened():
            self._cap.release()
            raise SourceError(f"could not open camera source '{source}'")

        self._frame: np.ndarray | None = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self.last_access = time.monotonic()
        self.error: str | None = None
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        misses = 0
        while not self._stop.is_set():
            ok, frame = self._cap.read()
            if ok and frame is not None:
                misses = 0
                with self._lock:
                    self._frame = frame
            else:
                misses += 1
                if misses > 50:
                    self.error = "camera stopped returning frames"
                    break
                time.sleep(0.05)
            if time.monotonic() - self.last_access > _IDLE_TIMEOUT_S:
                break
        self._cap.release()

    def read(self, timeout_s: float = 3.0) -> np.ndarray:
        self.last_access = time.monotonic()
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            with self._lock:
                if self._frame is not None:
                    return self._frame.copy()
            if self.error:
                raise SourceError(self.error)
            time.sleep(0.05)
        raise SourceError(f"no frame from '{self.source}' within {timeout_s}s")

    @property
    def alive(self) -> bool:
        return self._thread.is_alive() and not self._stop.is_set()

    def stop(self) -> None:
        self._stop.set()


class CameraHub:
    def __init__(self) -> None:
        self._feeds: dict[str, _Feed] = {}
        self._lock = threading.Lock()

    def _feed(self, source: str) -> _Feed:
        with self._lock:
            feed = self._feeds.get(source)
            if feed is None or not feed.alive:
                if feed is not None:
                    feed.stop()
                feed = _Feed(source)
                self._feeds[source] = feed
            return feed

    def frame(self, source: str, timeout_s: float = 3.0) -> np.ndarray:
        return self._feed(source).read(timeout_s)

    def release_all(self) -> None:
        with self._lock:
            for feed in self._feeds.values():
                feed.stop()
            self._feeds.clear()


_HUB: CameraHub | None = None


def get_hub() -> CameraHub:
    global _HUB
    if _HUB is None:
        _HUB = CameraHub()
    return _HUB
