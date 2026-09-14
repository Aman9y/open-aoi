"""Filesystem-backed reference store.

Layout:  data/references/<REF_ID>/reference.png
                                 /meta.json      (Reference model, incl. regions)

Keeping references as plain files (not DB rows) makes them easy to inspect, edit
by hand, version, and ship as demo fixtures.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import cv2
import numpy as np

from ..config import Settings
from ..logging_config import get_logger
from ..profiles.base import InspectionProfile
from ..schemas.reference import Reference, ReferenceCreate

log = get_logger(__name__)

_ID_OK = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-")


class ReferenceError(RuntimeError):
    pass


class ReferenceRepository:
    def __init__(self, cfg: Settings) -> None:
        self._cfg = cfg
        self._root = cfg.references_dir
        self._root.mkdir(parents=True, exist_ok=True)

    # ---- helpers --------------------------------------------------------------
    def _dir(self, ref_id: str) -> Path:
        return self._root / ref_id

    @staticmethod
    def _validate_id(ref_id: str) -> None:
        if not ref_id or not set(ref_id) <= _ID_OK:
            raise ReferenceError(
                "Reference id must be non-empty and use only letters, digits, '_' and '-'"
            )

    def _meta_path(self, ref_id: str) -> Path:
        return self._dir(ref_id) / "meta.json"

    # ---- reads --------------------------------------------------------------
    def list(self) -> list[Reference]:
        refs: list[Reference] = []
        for meta in sorted(self._root.glob("*/meta.json")):
            try:
                refs.append(Reference.model_validate_json(meta.read_text("utf-8")))
            except Exception as exc:  # noqa: BLE001 - keep listing others
                log.warning("skipping malformed reference %s: %s", meta.parent.name, exc)
        return refs

    def get(self, ref_id: str) -> Reference:
        path = self._meta_path(ref_id)
        if not path.is_file():
            raise ReferenceError(f"Reference '{ref_id}' not found")
        return Reference.model_validate_json(path.read_text("utf-8"))

    def get_active(self) -> Reference | None:
        for ref in self.list():
            if ref.active:
                return ref
        return None

    def load_profile(self, ref_id: str | None) -> InspectionProfile:
        if ref_id:
            ref = self.get(ref_id)
        else:
            ref = self.get_active()
            if ref is None:
                raise ReferenceError("No reference_id given and no active reference is set")
        return InspectionProfile(reference=ref, reference_dir=self._dir(ref.id))

    # ---- writes --------------------------------------------------------------
    def create(self, spec: ReferenceCreate, image: np.ndarray) -> Reference:
        self._validate_id(spec.id)
        rdir = self._dir(spec.id)
        if rdir.exists():
            raise ReferenceError(f"Reference '{spec.id}' already exists")
        rdir.mkdir(parents=True)

        img_path = rdir / "reference.png"
        ok, buf = cv2.imencode(".png", image)
        if not ok:
            raise ReferenceError("Could not encode reference image")
        img_path.write_bytes(buf.tobytes())

        ref = Reference(
            id=spec.id,
            name=spec.name,
            kind=spec.kind,
            inspection_mode=spec.inspection_mode,
            active=False,
            image_path=f"/media/references/{spec.id}/reference.png",
            regions=spec.regions,
            mm_per_px=spec.mm_per_px,
            created_at=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            notes=spec.notes,
        )
        self._write(ref)
        log.info("created reference %s (%d regions)", ref.id, len(ref.regions))
        return ref

    def set_regions(self, ref_id: str, regions: list) -> Reference:
        ref = self.get(ref_id)
        ref.regions = regions
        self._write(ref)
        return ref

    def activate(self, ref_id: str) -> Reference:
        target = self.get(ref_id)
        for ref in self.list():
            if ref.active and ref.id != ref_id:
                ref.active = False
                self._write(ref)
        target.active = True
        self._write(target)
        log.info("active reference is now %s", ref_id)
        return target

    def delete(self, ref_id: str) -> None:
        rdir = self._dir(ref_id)
        if not rdir.exists():
            raise ReferenceError(f"Reference '{ref_id}' not found")
        for p in sorted(rdir.rglob("*"), reverse=True):
            p.unlink()
        rdir.rmdir()

    def _write(self, ref: Reference) -> None:
        self._meta_path(ref.id).write_text(
            json.dumps(json.loads(ref.model_dump_json()), indent=2), "utf-8"
        )
