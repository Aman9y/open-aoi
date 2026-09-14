"""Inspection history + analytics + CSV export."""

from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.responses import PlainTextResponse

from ..schemas.inspection import InspectionStatus
from .deps import inspection_repo

router = APIRouter(prefix="/api", tags=["history"])


@router.get("/inspections")
def list_inspections(
    status: InspectionStatus | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    limit: int = Query(default=200, le=1000),
    offset: int = Query(default=0, ge=0),
) -> list[dict]:
    return inspection_repo().list(
        status=status.value if status else None,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )


@router.get("/stats")
def stats(date_from: str | None = Query(default=None)) -> dict:
    return inspection_repo().stats(date_from=date_from)


@router.get("/inspections.csv", response_class=PlainTextResponse)
def export_csv(
    status: InspectionStatus | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
) -> PlainTextResponse:
    csv_text = inspection_repo().export_csv(
        status=status.value if status else None,
        date_from=date_from,
        date_to=date_to,
    )
    return PlainTextResponse(
        csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=inspections.csv"},
    )
