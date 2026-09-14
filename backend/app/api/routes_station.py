"""Physical inspection-station endpoints (ESP32 over Wi-Fi).

    GET  /api/station/state    <- ESP32 polls this to drive LEDs / servo / buzzer
    POST /api/station/trigger  <- ESP32 button / sensor, or the dashboard button
"""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Request

from ..logging_config import get_logger
from ..schemas.inspection import InspectionResult, MultiViewResult
from ..sources import SourceError
from ..sources.camera_hub import get_hub
from ..station import get_station
from .deps import settings
from .routes_inspection import ViewSpec, inspect_array, run_multiview_request

router = APIRouter(prefix="/api/station", tags=["station"])
log = get_logger(__name__)


@router.get("/state")
def station_state(request: Request) -> dict:
    st = get_station()
    # Only the ESP32 sends ?client=esp32 — the dashboard polling this must NOT
    # count as the hardware checking in.
    if request.query_params.get("client") == "esp32":
        st.note_esp32_poll()
    return asdict(st.state())


@router.post("/trigger", response_model=InspectionResult | MultiViewResult)
def station_trigger() -> InspectionResult | MultiViewResult:
    """Trigger an inspection using the configured station camera(s).

    Multi-camera when ``AOI_STATION_VIEWS`` is set, else the single
    ``AOI_STATION_SOURCE``.
    """
    cfg = settings()
    station = get_station()
    if not station.enabled:
        raise HTTPException(status_code=409, detail="Station is not enabled (AOI_STATION_ENABLED)")

    if cfg.station_views:
        views = [ViewSpec(**v) for v in cfg.station_views]
        return run_multiview_request(views, save=True)

    if not station.source:
        raise HTTPException(
            status_code=409,
            detail="No station camera configured (AOI_STATION_SOURCE or AOI_STATION_VIEWS)",
        )
    try:
        frame = get_hub().frame(station.source, timeout_s=6.0)
    except SourceError as exc:
        raise HTTPException(status_code=502, detail=f"station camera: {exc}") from exc
    return inspect_array(
        frame, station.reference_id or cfg.station_reference_id, "station", save=True
    )
