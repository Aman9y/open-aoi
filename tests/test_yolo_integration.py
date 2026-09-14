"""Stage F.5 — object-detector (YOLO) corroboration.

Uses a scripted fake detector; the real Ultralytics dependency is optional and
never imported here. Verifies: model-disabled fallback, MODEL NOT CONFIGURED,
WRONG_COMPONENT, and the template-match-vs-detector contradiction -> REVIEW.
"""

from __future__ import annotations

import pytest

from app.models.component_detector import ComponentDetector, Detection
from app.schemas.defect import DefectType
from app.schemas.inspection import InspectionStatus, ModelStatus, ReasonCode


def _profile(env):
    from app.storage.reference_repository import ReferenceRepository

    return ReferenceRepository(env).load_profile(None)


def _run(env, image):
    from app.config import get_settings
    from app.inspection.pipeline import run_inspection

    return run_inspection(image, _profile(env), get_settings())


class FakeDetector(ComponentDetector):
    def __init__(self, dets: list[Detection]) -> None:
        self._dets = dets

    @property
    def status(self) -> str:
        return "READY"

    def detect(self, image_bgr):  # noqa: ANN001
        return list(self._dets)


def _region_xyxy(gen, name: str) -> tuple[int, int, int, int]:
    for n, (x, y, w, h), _kind in gen.COMPONENTS:
        if n == name:
            return (x, y, x + w, y + h)
    raise KeyError(name)


# ---- 1. model disabled -> deterministic only, unchanged ---------------
def test_model_disabled_is_deterministic_only(reference):
    env, gen = reference
    res = _run(env, gen.perturb(gen.render_board(seed=2), tx=3))
    assert res.model_status == ModelStatus.DETERMINISTIC_ONLY
    assert res.status == InspectionStatus.GOOD
    assert res.detections == []


# ---- 2. model path set but missing -> MODEL NOT CONFIGURED -----------
def test_missing_model_file_reports_not_configured(reference, monkeypatch, tmp_path):
    env, gen = reference
    from app.config import get_settings
    from app.models import reset_detector_cache

    monkeypatch.setenv("AOI_YOLO_MODEL_PATH", str(tmp_path / "nope.pt"))
    get_settings.cache_clear()
    reset_detector_cache()

    res = _run(env, gen.perturb(gen.render_board(seed=2), tx=3))
    assert res.model_status == ModelStatus.MODEL_NOT_CONFIGURED
    # deterministic verdict still produced, nothing faked
    assert res.status == InspectionStatus.GOOD

    get_settings.cache_clear()
    reset_detector_cache()


# ---- 3. wrong component -> DEFECTIVE / WRONG_COMPONENT ---------------
def test_wrong_component_class(reference, monkeypatch):
    env, gen = reference
    # A physically fine board, but the detector says R17's slot holds a capacitor.
    dets = [Detection(label="cap", confidence=0.93, bbox=_region_xyxy(gen, "R17"))]
    monkeypatch.setattr(
        "app.inspection.pipeline.build_component_detector", lambda cfg: FakeDetector(dets)
    )
    res = _run(env, gen.perturb(gen.render_board(seed=2), tx=3))

    assert res.model_status == ModelStatus.YOLO_ACTIVE
    assert res.status == InspectionStatus.DEFECTIVE
    wrong = [d for d in res.defects if d.type == DefectType.WRONG_COMPONENT]
    assert wrong and wrong[0].component == "R17"


# ---- 4. detector contradicts a MISSING call -> REVIEW ---------------
def test_detector_contradiction_is_review(reference, monkeypatch):
    env, gen = reference
    # R17 really is absent (template match -> MISSING) but the detector "sees" one.
    dets = [Detection(label="resistor", confidence=0.9, bbox=_region_xyxy(gen, "R17"))]
    monkeypatch.setattr(
        "app.inspection.pipeline.build_component_detector", lambda cfg: FakeDetector(dets)
    )
    res = _run(env, gen.perturb(gen.render_board(skip={"R17"}, seed=3)))

    assert res.status == InspectionStatus.REVIEW
    assert res.reason == ReasonCode.CONTRADICTORY
    r17 = next(m for m in res.regions if m.name == "R17")
    assert r17.detector_agreement == "conflict"


# ---- 5. detector agrees -> still GOOD, corroboration recorded --------
def test_detector_agreement_keeps_good(reference, monkeypatch):
    env, gen = reference
    dets = [
        Detection(label=kind if kind != "cap" else "cap", confidence=0.88,
                  bbox=_region_xyxy(gen, name))
        for name, _box, kind in gen.COMPONENTS
    ]
    monkeypatch.setattr(
        "app.inspection.pipeline.build_component_detector", lambda cfg: FakeDetector(dets)
    )
    res = _run(env, gen.perturb(gen.render_board(seed=2), tx=3))

    assert res.status == InspectionStatus.GOOD
    assert res.model_status == ModelStatus.YOLO_ACTIVE
    assert any(m.detector_agreement == "agree" for m in res.regions)
    assert len(res.detections) >= 5


@pytest.fixture(autouse=True)
def _clear_detector_cache():
    from app.models import reset_detector_cache

    reset_detector_cache()
    yield
    reset_detector_cache()
