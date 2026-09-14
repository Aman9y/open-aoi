"""Inspection endpoints."""

from __future__ import annotations

import numpy as np
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from ..inspection.multiview import run_multiview
from ..inspection.pipeline import run_inspection
from ..logging_config import get_logger
from ..schemas.inspection import InspectionResult, MultiViewResult
from ..sources import SourceError, UploadSource
from ..sources.camera_hub import get_hub
from ..station import get_station
from ..storage.reference_repository import ReferenceError
from .deps import inspection_repo, reference_repo, settings

router = APIRouter(prefix="/api/inspections", tags=["inspection"])
log = get_logger(__name__)


def inspect_array(
    image: np.ndarray, reference_id: str | None, filename: str, *, save: bool = True
) -> InspectionResult:
    cfg = settings()
    try:
        profile = reference_repo().load_profile(reference_id)
    except ReferenceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        result = run_inspection(image, profile, cfg, original_filename=filename)
    except Exception as exc:  # noqa: BLE001 - surface a clean 500
        log.exception("inspection failed")
        raise HTTPException(status_code=500, detail=f"Inspection failed: {exc}") from exc

    if save:
        inspection_repo().save(result)
    station = get_station()
    if station.enabled:
        station.record(result)
    return result


@router.post("/inspect", response_model=InspectionResult)
async def inspect(
    file: UploadFile = File(...),
    reference_id: str | None = Form(default=None),
    save: bool = Form(default=True),
) -> InspectionResult:
    payload = await file.read()
    try:
        image = UploadSource(payload, file.filename or "upload").read()
    except SourceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return inspect_array(image, reference_id, file.filename or "", save=save)


class LiveInspectRequest(BaseModel):
    source: str  # local device index ("0") or stream URL
    reference_id: str | None = None
    save: bool = True  # live-polling clients pass false; "Record" passes true


@router.post("/inspect_live", response_model=InspectionResult)
def inspect_live(req: LiveInspectRequest) -> InspectionResult:
    """Grab one frame from a live camera / phone stream and inspect it.

    With ``save=false`` (continuous live mode) the result is returned but not
    written to history, so a running feed does not flood the log.
    """
    try:
        frame = get_hub().frame(req.source, timeout_s=6.0)
    except SourceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return inspect_array(frame, req.reference_id, f"live:{req.source}", save=req.save)


class ViewSpec(BaseModel):
    name: str
    source: str                     # camera index ("0") or stream URL
    reference_id: str | None = None


class MultiInspectRequest(BaseModel):
    views: list[ViewSpec] = Field(min_length=1, max_length=4)
    save: bool = True


def run_multiview_request(views: list[ViewSpec], *, save: bool) -> MultiViewResult:
    hub = get_hub()
    items = []
    for v in views:
        try:
            frame = hub.frame(v.source, timeout_s=6.0)
        except SourceError as exc:
            raise HTTPException(status_code=502, detail=f"view '{v.name}': {exc}") from exc
        try:
            profile = reference_repo().load_profile(v.reference_id)
        except ReferenceError as exc:
            raise HTTPException(status_code=400, detail=f"view '{v.name}': {exc}") from exc
        items.append((v.name, frame, profile, v.source))

    try:
        mv = run_multiview(items, settings())
    except Exception as exc:  # noqa: BLE001
        log.exception("multi-view inspection failed")
        raise HTTPException(status_code=500, detail=f"Multi-view inspection failed: {exc}") from exc

    if save:
        inspection_repo().save_multi(mv)
    station = get_station()
    if station.enabled:
        station.record(mv)
    return mv


@router.post("/inspect_multi", response_model=MultiViewResult)
def inspect_multi(req: MultiInspectRequest) -> MultiViewResult:
    """Inspect one object from several cameras at once; verdict = worst view."""
    return run_multiview_request(req.views, save=req.save)


@router.get("/{inspection_id}", response_model=InspectionResult | MultiViewResult)
def get_inspection(inspection_id: str) -> InspectionResult | MultiViewResult:
    result = inspection_repo().get(inspection_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Inspection not found")
    return result
