"""End-to-end engine: image + profile -> real GOOD / DEFECTIVE / REVIEW."""

from __future__ import annotations

from app.schemas.defect import DefectType
from app.schemas.inspection import InspectionStatus, ReasonCode


def _run(reference, image):
    env, _ = reference
    from app.config import get_settings
    from app.inspection.pipeline import run_inspection
    from app.storage.reference_repository import ReferenceRepository

    profile = ReferenceRepository(env).load_profile(None)
    return run_inspection(image, profile, get_settings())


def test_good_board_passes(reference):
    _, gen = reference
    res = _run(reference, gen.perturb(gen.render_board(seed=2), tx=4, ty=-3, angle=0.8))
    assert res.status == InspectionStatus.GOOD
    assert res.reason == ReasonCode.OK
    assert not res.defects


def test_missing_component_is_defective(reference):
    _, gen = reference
    res = _run(reference, gen.perturb(gen.render_board(skip={"R17"}, seed=3)))
    assert res.status == InspectionStatus.DEFECTIVE
    types = {(d.component, d.type) for d in res.defects}
    assert ("R17", DefectType.MISSING_COMPONENT) in types


def test_shifted_component_is_defective(reference):
    _, gen = reference
    res = _run(reference, gen.perturb(gen.render_board(shift={"C4": (22, 14)}, seed=4)))
    assert res.status == InspectionStatus.DEFECTIVE
    shifted = [d for d in res.defects if d.type == DefectType.SHIFTED_COMPONENT]
    assert shifted and shifted[0].component == "C4"
    assert shifted[0].deviation_px and shifted[0].deviation_px > shifted[0].allowed_px


def test_rotated_component_is_defective(reference):
    _, gen = reference
    res = _run(reference, gen.perturb(gen.render_board(rotate={"IC2": 18.0}, seed=5)))
    assert res.status == InspectionStatus.DEFECTIVE
    rotated = [d for d in res.defects if d.type == DefectType.ROTATED_COMPONENT]
    assert rotated and rotated[0].component == "IC2"


def test_blurred_image_is_review_not_good(reference):
    _, gen = reference
    res = _run(reference, gen.perturb(gen.render_board(seed=6), blur=13))
    assert res.status == InspectionStatus.REVIEW
    assert res.reason == ReasonCode.POOR_IMAGE_QUALITY


def test_misaligned_image_is_review_not_good(reference):
    _, gen = reference
    res = _run(reference, gen.perturb(gen.render_board(seed=7), tx=180, ty=120, angle=27.0))
    assert res.status == InspectionStatus.REVIEW
    assert res.reason == ReasonCode.ALIGNMENT_FAILED


def test_uncertainty_never_becomes_good(reference):
    """The core safety property: REVIEW/DEFECTIVE inputs never read GOOD."""
    _, gen = reference
    for img in (
        gen.perturb(gen.render_board(seed=6), blur=15),
        gen.perturb(gen.render_board(seed=7), tx=190, angle=28.0),
        gen.perturb(gen.render_board(skip={"IC1"}, seed=8)),
    ):
        assert _run(reference, img).status != InspectionStatus.GOOD
