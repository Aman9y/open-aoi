"""Stage A.2 — board detection / cropping on simulated camera photos."""

from __future__ import annotations

import cv2
import numpy as np


def _cfg(reference):
    from app.config import get_settings

    return get_settings()


def test_detects_board_in_cluttered_scene(reference):
    _, gen = reference
    cfg = _cfg(reference)
    from app.inspection.detection import detect_board

    photo = gen.photograph(gen.render_board(seed=2), seed=101, scale=0.6, angle=6)
    cropped, det = detect_board(photo, cfg, reference_aspect=900 / 640)

    assert det.found and det.method in {"quad", "color"}
    assert 0.1 < det.coverage < 0.9
    # crop is tighter than the original frame and roughly board-shaped
    assert cropped.shape[0] < photo.shape[0] and cropped.shape[1] < photo.shape[1]
    aspect = cropped.shape[1] / cropped.shape[0]
    assert 0.9 < aspect < 1.9


def test_passthrough_when_board_fills_frame(reference):
    _, gen = reference
    cfg = _cfg(reference)
    from app.inspection.detection import detect_board

    board = gen.render_board(seed=1)  # already tightly framed
    out, det = detect_board(board, cfg, reference_aspect=900 / 640)

    assert not det.found
    assert out.shape == board.shape  # unchanged


def test_passthrough_when_nothing_boardlike(reference):
    cfg = _cfg(reference)
    from app.inspection.detection import detect_board

    noise = np.random.default_rng(0).integers(0, 255, (700, 900, 3), dtype=np.uint8)
    out, det = detect_board(noise, cfg, reference_aspect=1.4)

    assert not det.found
    assert out.shape == noise.shape


def test_detection_feeds_a_working_pipeline(reference):
    """A photographed defective board still yields the right verdict end-to-end."""
    env, gen = reference
    from app.config import get_settings
    from app.inspection.pipeline import run_inspection
    from app.storage.reference_repository import ReferenceRepository

    profile = ReferenceRepository(env).load_profile(None)
    photo = gen.photograph(gen.render_board(skip={"R17"}, seed=3), seed=104, angle=5)
    res = run_inspection(photo, profile, get_settings())

    assert res.detection.found
    assert res.status.value == "DEFECTIVE"
    assert any(d.component == "R17" for d in res.defects)
    assert res.montage_image_path and res.cropped_image_path
