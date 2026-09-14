"""Stage C — alignment behaviour under translation / rotation / failure."""

from __future__ import annotations

import numpy as np


def _cfg_and_ref(reference):
    env, gen = reference
    from app.config import get_settings

    cfg = get_settings()
    ref = gen.render_board(seed=1)
    return cfg, gen, ref


def test_aligns_translated_board(reference):
    cfg, gen, ref = _cfg_and_ref(reference)
    from app.inspection.alignment import align_to_reference

    test = gen.perturb(gen.render_board(seed=2), tx=40, ty=-25)
    _, meta = align_to_reference(test, ref, cfg)

    assert meta.success
    assert meta.alignment_error_px < cfg.align_max_error_px
    assert meta.inliers >= cfg.align_min_inliers


def test_aligns_rotated_board(reference):
    cfg, gen, ref = _cfg_and_ref(reference)
    from app.inspection.alignment import align_to_reference

    test = gen.perturb(gen.render_board(seed=3), angle=6.0)
    _, meta = align_to_reference(test, ref, cfg)

    assert meta.success
    assert abs(meta.rotation_deg) > 3.0  # detected the rotation
    assert abs(abs(meta.rotation_deg) - 6.0) < 2.5  # roughly correct


def test_alignment_fails_on_unrelated_image(reference):
    cfg, gen, ref = _cfg_and_ref(reference)
    from app.inspection.alignment import align_to_reference

    noise = np.random.default_rng(0).integers(0, 255, ref.shape, dtype=np.uint8)
    _, meta = align_to_reference(noise, ref, cfg)

    assert not meta.success
    assert meta.reason


def test_alignment_fails_on_severe_misalignment(reference):
    cfg, gen, ref = _cfg_and_ref(reference)
    from app.inspection.alignment import align_to_reference

    test = gen.perturb(gen.render_board(seed=4), tx=200, ty=160, angle=30.0)
    _, meta = align_to_reference(test, ref, cfg)

    assert not meta.success  # rotation clamp rejects it
