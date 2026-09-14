"""API smoke tests via FastAPI TestClient."""

from __future__ import annotations

import cv2
import numpy as np
from fastapi.testclient import TestClient


def _client(reference):
    from app.main import create_app

    return TestClient(create_app())


def _png(img: np.ndarray) -> bytes:
    return cv2.imencode(".png", img)[1].tobytes()


def test_health(reference):
    r = _client(reference).get("/api/health")
    assert r.status_code == 200
    assert r.json()["yolo"] == "MODEL NOT CONFIGURED"


def test_reference_is_listed_and_active(reference):
    c = _client(reference)
    refs = c.get("/api/references").json()
    assert len(refs) == 1 and refs[0]["active"]


def test_inspect_endpoint_returns_real_verdict(reference):
    _, gen = reference
    c = _client(reference)
    img = gen.perturb(gen.render_board(skip={"R17"}, seed=3))

    r = c.post("/api/inspections/inspect", files={"file": ("t.png", _png(img), "image/png")})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "DEFECTIVE"
    assert any(d["component"] == "R17" for d in body["defects"])
    assert body["model_status"] == "DETERMINISTIC_ONLY"

    # recorded in history
    hist = c.get("/api/inspections").json()
    assert hist[0]["inspection_id"] == body["inspection_id"]

    # annotated media is served
    assert c.get(body["annotated_image_path"]).status_code == 200


def test_inspect_rejects_non_image(reference):
    c = _client(reference)
    r = c.post("/api/inspections/inspect", files={"file": ("x.txt", b"not an image", "text/plain")})
    assert r.status_code == 422


def test_camera_devices_endpoint(reference):
    r = _client(reference).get("/api/camera/devices?max_index=0")
    assert r.status_code == 200
    assert isinstance(r.json(), list)  # may be empty on a headless box


def test_inspect_live_bad_source_is_502(reference):
    # device index 987 will not open -> clean 502, no fake result
    r = _client(reference).post(
        "/api/inspections/inspect_live", json={"source": "987"}
    )
    assert r.status_code == 502


def test_csv_export(reference):
    _, gen = reference
    c = _client(reference)
    c.post("/api/inspections/inspect",
           files={"file": ("t.png", _png(gen.render_board(seed=2)), "image/png")})
    r = c.get("/api/inspections.csv")
    assert r.status_code == 200
    assert "inspection_id" in r.text
