"""The same engine, a different product — a printed carton.

Proves the pipeline is profile-driven: no PCB-specific code path is taken.
"""

from __future__ import annotations

import pytest

from app.schemas.defect import DefectType
from app.schemas.inspection import InspectionStatus
from app.schemas.reference import ProfileKind, ReferenceCreate


@pytest.fixture()
def box(env):
    import make_synthetic_box as gen
    from app.storage.reference_repository import ReferenceRepository

    repo = ReferenceRepository(env)
    repo.create(
        ReferenceCreate(
            id=gen.REF_ID, name="Test Carton", kind=ProfileKind.BOX,
            regions=gen.regions(), mm_per_px=0.2,
        ),
        gen.render_box(seed=1),
    )
    repo.activate(gen.REF_ID)
    return env, gen


def _run(env, image):
    from app.config import get_settings
    from app.inspection.pipeline import run_inspection
    from app.storage.reference_repository import ReferenceRepository

    profile = ReferenceRepository(env).load_profile(None)
    return run_inspection(image, profile, get_settings())


def test_good_carton_passes(box):
    env, gen = box
    res = _run(env, gen.photograph(gen.render_box(seed=2), seed=201, angle=5, surface="mat"))
    assert res.profile_kind == "BOX"
    assert res.status == InspectionStatus.GOOD


def test_missing_cap_is_defective(box):
    env, gen = box
    res = _run(env, gen.photograph(gen.render_box(skip={"CAP"}, seed=3), seed=203,
                                   angle=4, surface="mat"))
    assert res.status == InspectionStatus.DEFECTIVE
    assert any(d.component == "CAP" and d.type == DefectType.MISSING_COMPONENT
               for d in res.defects)


def test_crooked_label_is_rotation_defect(box):
    env, gen = box
    res = _run(env, gen.photograph(gen.render_box(rotate={"LABEL": 13.0}, seed=7),
                                   seed=207, angle=-3, surface="mat"))
    assert res.status == InspectionStatus.DEFECTIVE
    assert any(d.component == "LABEL" and d.type == DefectType.ROTATED_COMPONENT
               for d in res.defects)


def test_wrong_cap_colour_is_anomaly(box):
    env, gen = box
    res = _run(env, gen.photograph(gen.render_box(cap_color=(70, 160, 70), seed=10),
                                   seed=209, angle=-4, surface="mat"))
    assert res.status == InspectionStatus.DEFECTIVE
    assert any(d.component == "CAP" and d.type == DefectType.VISUAL_ANOMALY
               for d in res.defects)
