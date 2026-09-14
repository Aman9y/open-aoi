"""Reference (known-good board) management endpoints."""

from __future__ import annotations

import json

from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile
from pydantic import BaseModel

from ..logging_config import get_logger
from ..schemas.reference import (
    InspectionMode,
    ProfileKind,
    Reference,
    ReferenceCreate,
    Region,
)
from ..sources import SourceError, UploadSource
from ..sources.camera_hub import get_hub
from ..storage.reference_repository import ReferenceError
from .deps import reference_repo

router = APIRouter(prefix="/api/references", tags=["reference"])
log = get_logger(__name__)


@router.get("", response_model=list[Reference])
def list_references() -> list[Reference]:
    return reference_repo().list()


@router.get("/active", response_model=Reference | None)
def active_reference() -> Reference | None:
    return reference_repo().get_active()


@router.get("/{reference_id}", response_model=Reference)
def get_reference(reference_id: str) -> Reference:
    try:
        return reference_repo().get(reference_id)
    except ReferenceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("", response_model=Reference, status_code=201)
async def create_reference(
    file: UploadFile = File(...),
    id: str = Form(...),
    name: str = Form(...),
    kind: ProfileKind = Form(default=ProfileKind.PCB),
    inspection_mode: InspectionMode = Form(default=InspectionMode.REGIONS),
    regions: str = Form(default="[]"),
    mm_per_px: float | None = Form(default=None),
    notes: str = Form(default=""),
    activate: bool = Form(default=False),
) -> Reference:
    try:
        region_list = [Region.model_validate(r) for r in json.loads(regions or "[]")]
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"Invalid regions JSON: {exc}") from exc

    try:
        image = UploadSource(await file.read(), file.filename or "reference").read()
    except SourceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    spec = ReferenceCreate(
        id=id, name=name, kind=kind, inspection_mode=inspection_mode,
        regions=region_list, mm_per_px=mm_per_px, notes=notes,
    )
    try:
        ref = reference_repo().create(spec, image)
        if activate:
            ref = reference_repo().activate(ref.id)
    except ReferenceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ref


_CLASS_PREFIX = {"resistor": "R", "cap": "C", "ic": "U", "led": "D", "connector": "J"}


@router.post("/{reference_id}/autodetect_regions", response_model=list[Region])
def autodetect_regions(reference_id: str) -> list[Region]:
    """Propose inspection regions for a reference using the YOLO detector.

    Returns candidates only — the caller reviews/edits and PUTs them back.
    400 with 'MODEL NOT CONFIGURED' if no detector is available.
    """
    from ..config import get_settings
    from ..models import MODEL_NOT_CONFIGURED, build_component_detector
    from ..schemas.reference import RegionTolerances

    cfg = get_settings()
    detector = build_component_detector(cfg)
    if detector.status == MODEL_NOT_CONFIGURED:
        raise HTTPException(status_code=400, detail="MODEL NOT CONFIGURED")

    try:
        profile = reference_repo().load_profile(reference_id)
    except ReferenceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    dets = sorted(detector.detect(profile.load_reference_image()),
                  key=lambda d: (d.bbox[1], d.bbox[0]))
    counters: dict[str, int] = {}
    regions: list[Region] = []
    for d in dets:
        prefix = _CLASS_PREFIX.get(d.label, "X")
        counters[prefix] = counters.get(prefix, 0) + 1
        x1, y1, x2, y2 = d.bbox
        regions.append(
            Region(
                name=f"{prefix}{counters[prefix]}",
                bbox=(x1, y1, x2 - x1, y2 - y1),
                expected_class=d.label,
                tolerances=RegionTolerances(check_rotation=d.label != "led"),
            )
        )
    return regions


class CaptureReferenceRequest(BaseModel):
    id: str
    name: str
    source: str                         # camera index ("0") or stream URL
    kind: ProfileKind = ProfileKind.PCB
    inspection_mode: InspectionMode = InspectionMode.SURFACE  # capture -> usually a whole object
    mm_per_px: float | None = None
    activate: bool = True


@router.post("/capture", response_model=Reference, status_code=201)
def capture_reference(req: CaptureReferenceRequest) -> Reference:
    """Grab one frame from a live camera and save it as a new reference.

    Use this to inspect a REAL object: the synthetic demo references only match
    the synthetic images. Capture your known-good part through the same camera you
    will inspect with, then add regions.
    """
    try:
        frame = get_hub().frame(req.source, timeout_s=6.0)
    except SourceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    spec = ReferenceCreate(
        id=req.id, name=req.name, kind=req.kind, inspection_mode=req.inspection_mode,
        regions=[], mm_per_px=req.mm_per_px,
        notes=f"captured from camera source '{req.source}'",
    )
    try:
        ref = reference_repo().create(spec, frame)
        if req.activate:
            ref = reference_repo().activate(ref.id)
    except ReferenceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ref


@router.put("/{reference_id}/regions", response_model=Reference)
def set_regions(reference_id: str, regions: list[Region]) -> Reference:
    try:
        return reference_repo().set_regions(reference_id, regions)
    except ReferenceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{reference_id}/activate", response_model=Reference)
def activate_reference(reference_id: str) -> Reference:
    try:
        return reference_repo().activate(reference_id)
    except ReferenceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{reference_id}")
def delete_reference(reference_id: str) -> Response:
    try:
        reference_repo().delete(reference_id)
    except ReferenceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(status_code=204)
