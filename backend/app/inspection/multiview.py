"""Inspect one object with several cameras at once, and combine to one verdict.

Each view is a full, independent single-view inspection (`run_inspection`) — its
own alignment, region checks, defects, saved media. This module only fans them
out and combines:

  * status  = worst of the per-view statuses (DEFECTIVE > REVIEW > GOOD)
  * defects = union, each component prefixed with its view name
  * confidence = the lowest per-view confidence
"""

from __future__ import annotations

import datetime as dt
import time
import uuid

import cv2
import numpy as np

from ..config import Settings
from ..logging_config import get_logger
from ..profiles.base import InspectionProfile
from ..schemas.defect import Defect
from ..schemas.inspection import (
    InspectionStatus,
    MultiViewResult,
    ReasonCode,
    ViewResult,
)
from .pipeline import run_inspection
from .visualization import montage

log = get_logger(__name__)

_RANK = {InspectionStatus.GOOD: 0, InspectionStatus.REVIEW: 1, InspectionStatus.DEFECTIVE: 2}


def run_multiview(
    items: list[tuple[str, np.ndarray, InspectionProfile, str]],
    cfg: Settings,
) -> MultiViewResult:
    """items: list of (view_name, image_bgr, profile, source_str)."""
    t0 = time.perf_counter()
    inspection_id = "MVI-" + dt.datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
    ts = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    out_dir = cfg.outputs_dir / inspection_id
    out_dir.mkdir(parents=True, exist_ok=True)

    views: list[ViewResult] = []
    for name, image, profile, source in items:
        res = run_inspection(image, profile, cfg, original_filename=f"view:{name}")
        views.append(ViewResult(name=name, source=source, result=res))

    worst = max((v.result.status for v in views), key=lambda s: _RANK[s])
    lead = next(v for v in views if v.result.status == worst)

    defects: list[Defect] = []
    for v in views:
        for d in v.result.defects:
            defects.append(d.model_copy(update={"component": f"{v.name}/{d.component}"}))

    parts = []
    for v in views:
        s = v.result.status.value
        extra = ""
        if v.result.defects:
            extra = " — " + ", ".join(
                f"{d.component} {d.type.value.replace('_', ' ').lower()}" for d in v.result.defects
            )
        elif not v.result.alignment.success:
            extra = f" — {v.result.alignment.reason}"
        parts.append(f"{v.name}: {s}{extra}")
    explanation = f"{len(views)} views — " + "; ".join(parts) + "."

    annotated = [
        cv2.imread(str(cfg.outputs_dir / v.result.inspection_id / "annotated.png"))
        for v in views
    ]
    annotated = [a for a in annotated if a is not None]
    if annotated:
        strip = montage(annotated, [f"{v.name} - {v.result.status.value}" for v in views])
        ok, buf = cv2.imencode(".png", strip)
        if ok:
            (out_dir / "montage.png").write_bytes(buf.tobytes())

    mv = MultiViewResult(
        inspection_id=inspection_id,
        timestamp=ts,
        reference_id=",".join(sorted({v.result.reference_id for v in views})),
        status=worst,
        reason=lead.result.reason if worst != InspectionStatus.GOOD else ReasonCode.OK,
        explanation=explanation,
        overall_confidence=round(min(v.result.overall_confidence for v in views), 3),
        inspection_time_ms=int((time.perf_counter() - t0) * 1000),
        view_count=len(views),
        defects=defects,
        views=views,
        montage_image_path=f"/media/outputs/{inspection_id}/montage.png" if annotated else "",
        model_status=views[0].result.model_status if views else None,
    )
    (out_dir / "result.json").write_text(mv.model_dump_json(indent=2), "utf-8")
    log.info("%s -> %s (%d views) conf=%.2f %dms",
             inspection_id, mv.status.value, mv.view_count, mv.overall_confidence,
             mv.inspection_time_ms)
    return mv
