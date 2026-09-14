"""Physical station: state tracking, reject flag, trigger endpoint."""

from __future__ import annotations

import cv2
import numpy as np
from fastapi.testclient import TestClient


def _client(reference):
    from app.main import create_app

    return TestClient(create_app())


def test_station_disabled_by_default(reference):
    r = _client(reference).get("/api/station/state")
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is False
    assert body["verdict"] == "IDLE"


def test_trigger_refused_when_disabled(reference):
    r = _client(reference).post("/api/station/trigger")
    assert r.status_code == 409


def test_station_records_verdict_and_reject_flag(reference, monkeypatch):
    env, gen = reference
    from app.config import get_settings
    from app.inspection.pipeline import run_inspection
    from app.station import get_station
    from app.storage.reference_repository import ReferenceRepository

    monkeypatch.setenv("AOI_STATION_ENABLED", "true")
    get_settings.cache_clear()
    # rebuild the singleton against the new settings
    import app.station.controller as ctrl
    ctrl._STATION = None

    station = get_station()
    assert station.enabled

    profile = ReferenceRepository(env).load_profile(None)
    good = run_inspection(gen.perturb(gen.render_board(seed=2), tx=3), profile, get_settings())
    bad = run_inspection(gen.perturb(gen.render_board(skip={"R17"}, seed=3)), profile, get_settings())

    station.record(good)
    s = station.state()
    assert s.counter == 1 and s.verdict == "GOOD" and s.reject is False

    station.record(bad)
    s = station.state()
    assert s.counter == 2 and s.verdict == "DEFECTIVE" and s.reject is True

    ctrl._STATION = None
    get_settings.cache_clear()


def test_trigger_runs_inspection_from_source(reference, monkeypatch, tmp_path):
    env, gen = reference
    from app.config import get_settings
    import app.station.controller as ctrl

    # a fake camera source: monkeypatch the hub to hand back a rendered board
    img = gen.perturb(gen.render_board(skip={"R17"}, seed=3))
    from app.sources import camera_hub

    monkeypatch.setattr(camera_hub.CameraHub, "frame", lambda self, src, timeout_s=6.0: img)
    monkeypatch.setenv("AOI_STATION_ENABLED", "true")
    monkeypatch.setenv("AOI_STATION_SOURCE", "fake")
    get_settings.cache_clear()
    ctrl._STATION = None

    c = _client(reference)
    r = c.post("/api/station/trigger")
    assert r.status_code == 200
    assert r.json()["status"] == "DEFECTIVE"

    state = c.get("/api/station/state").json()
    assert state["counter"] >= 1 and state["verdict"] == "DEFECTIVE" and state["reject"] is True
    # recorded in history like any inspection
    assert c.get("/api/inspections").json()[0]["inspection_id"] == r.json()["inspection_id"]

    ctrl._STATION = None
    get_settings.cache_clear()


def test_multiview_endpoint_combines_worst_view(reference, monkeypatch):
    env, gen = reference
    from app.config import get_settings

    good = gen.perturb(gen.render_board(seed=2), tx=3)
    bad = gen.perturb(gen.render_board(skip={"R17"}, seed=3))
    frames = {"front": good, "back": bad}

    from app.sources import camera_hub

    monkeypatch.setattr(
        camera_hub.CameraHub, "frame",
        lambda self, src, timeout_s=6.0: frames[src],
    )
    get_settings.cache_clear()

    c = _client(reference)
    r = c.post(
        "/api/inspections/inspect_multi",
        json={"views": [
            {"name": "front", "source": "front"},
            {"name": "back", "source": "back"},
        ]},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["result_type"] == "multi"
    assert body["status"] == "DEFECTIVE"           # worst of GOOD + DEFECTIVE
    assert body["view_count"] == 2
    assert {v["name"] for v in body["views"]} == {"front", "back"}
    assert any(d["component"].startswith("back/") for d in body["defects"])

    # stored + retrievable as a multi result
    got = c.get(f"/api/inspections/{body['inspection_id']}").json()
    assert got["result_type"] == "multi" and len(got["views"]) == 2

    get_settings.cache_clear()


def _png(img: np.ndarray) -> bytes:  # noqa: ARG001 - kept for parity with other test modules
    return cv2.imencode(".png", img)[1].tobytes()
