"""Surface inspection mode — whole-object clean vs damaged."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from app.schemas.inspection import InspectionStatus
from app.schemas.reference import InspectionMode, Reference


def _panel(damaged: bool, seed: int) -> np.ndarray:
    """A pale panel on a desk; 'damaged' = heavy dark scribbles all over it."""
    rng = np.random.default_rng(seed)
    frame = np.full((760, 1000, 3), (150, 165, 185), np.uint8)
    cx, cy = 500 + int(rng.integers(-30, 30)), 380 + int(rng.integers(-30, 30))
    obj = np.full((380, 380, 3), (236, 238, 240), np.uint8)
    obj = np.clip(obj.astype(np.int16) + rng.normal(0, 3, obj.shape), 0, 255).astype(np.uint8)
    cv2.rectangle(obj, (0, 0), (379, 379), (120, 120, 120), 3)  # edge for detection
    if damaged:
        for _ in range(350):
            p = (int(rng.integers(0, 380)), int(rng.integers(0, 380)))
            q = (p[0] + int(rng.integers(-40, 40)), p[1] + int(rng.integers(-40, 40)))
            cv2.line(obj, p, q, (25, 25, 25), 2)
    m = cv2.getRotationMatrix2D((190, 190), rng.uniform(-5, 5), 1.0)
    obj = cv2.warpAffine(obj, m, (380, 380), borderValue=(150, 165, 185))
    frame[cy - 190 : cy + 190, cx - 190 : cx + 190] = obj
    return frame


@pytest.fixture()
def surface_profile(env):
    from app.storage.reference_repository import ReferenceRepository

    repo = ReferenceRepository(env)
    from app.schemas.reference import ReferenceCreate

    repo.create(
        ReferenceCreate(id="PANEL", name="Panel", inspection_mode=InspectionMode.SURFACE),
        _panel(damaged=False, seed=1),
    )
    repo.activate("PANEL")
    return env


def _run(env, image):
    from app.config import get_settings
    from app.inspection.pipeline import run_inspection
    from app.storage.reference_repository import ReferenceRepository

    profile = ReferenceRepository(env).load_profile(None)
    return run_inspection(image, profile, get_settings())


def test_clean_surface_is_good(surface_profile):
    for seed in (2, 5, 9):
        res = _run(surface_profile, _panel(damaged=False, seed=seed))
        assert res.status == InspectionStatus.GOOD, f"seed {seed}: {res.explanation}"


def test_damaged_surface_is_defective(surface_profile):
    for seed in (3, 6, 8):
        res = _run(surface_profile, _panel(damaged=True, seed=seed))
        assert res.status == InspectionStatus.DEFECTIVE, f"seed {seed}: {res.explanation}"
        assert any(d.component == "SURFACE" for d in res.defects)


def test_reference_persists_inspection_mode(surface_profile):
    from app.storage.reference_repository import ReferenceRepository

    ref: Reference = ReferenceRepository(surface_profile).get("PANEL")
    assert ref.inspection_mode == InspectionMode.SURFACE
