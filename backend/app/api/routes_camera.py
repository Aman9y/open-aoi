"""Live camera endpoints: enumerate local devices, MJPEG preview proxy.

The actual "capture & inspect" call lives in ``routes_inspection`` as
``POST /api/inspections/inspect_live`` so it shares the inspection plumbing.
"""

from __future__ import annotations

import time

import cv2
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from ..logging_config import get_logger
from ..sources.camera_hub import get_hub
from ..sources.camera_source import _LOCAL_BACKEND

router = APIRouter(prefix="/api/camera", tags=["camera"])
log = get_logger(__name__)

_PREVIEW_FPS = 12


@router.get("/devices")
def list_devices(max_index: int = Query(default=5, le=10)) -> list[dict]:
    """Probe local capture device indices. Slow-ish (opens each) — call sparingly."""
    devices: list[dict] = []
    for i in range(max_index + 1):
        cap = cv2.VideoCapture(i, _LOCAL_BACKEND)
        try:
            if cap.isOpened():
                ok, frame = cap.read()
                if ok and frame is not None:
                    h, w = frame.shape[:2]
                    devices.append({"source": str(i), "label": f"Camera {i}", "width": w, "height": h})
        finally:
            cap.release()
    return devices


def _mjpeg(source: str):
    hub = get_hub()
    boundary = "frame"
    period = 1.0 / _PREVIEW_FPS
    while True:
        start = time.monotonic()
        try:
            frame = hub.frame(source, timeout_s=5.0)
        except Exception as exc:  # noqa: BLE001 - end the stream cleanly
            log.info("preview stream for %s ended: %s", source, exc)
            return
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
        if ok:
            yield (
                f"--{boundary}\r\nContent-Type: image/jpeg\r\n"
                f"Content-Length: {buf.size}\r\n\r\n".encode()
                + buf.tobytes()
                + b"\r\n"
            )
        elapsed = time.monotonic() - start
        if elapsed < period:
            time.sleep(period - elapsed)


@router.get("/preview")
def preview(source: str = Query(..., description="local device index or stream URL")):
    """MJPEG stream the browser can drop straight into an <img> tag."""
    if not source:
        raise HTTPException(status_code=422, detail="source is required")
    return StreamingResponse(
        _mjpeg(source),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-store"},
    )
