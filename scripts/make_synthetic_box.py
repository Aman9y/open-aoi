"""Second inspection profile — a printed carton / box.

Proves the engine is not PCB-specific: the exact same detect -> align -> compare
-> decide pipeline runs on a completely different object, driven only by this
profile's reference image + regions.

    py scripts/make_synthetic_box.py [--force]

Creates reference BOX_MODEL_001 (kind=BOX) and dataset data/datasets/box_v1/.
"""

from __future__ import annotations

import argparse
import random

import _bootstrap  # noqa: F401
import cv2
import numpy as np

from _scene import perturb, photograph, write_dataset  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.schemas.reference import (  # noqa: E402
    ProfileKind,
    Region,
    RegionTolerances,
    ReferenceCreate,
)
from app.storage.reference_repository import ReferenceRepository  # noqa: E402

_ = perturb  # re-exported for tests

REF_ID = "BOX_MODEL_001"
W, H = 640, 800
CARD = (150, 180, 205)  # BGR kraft/tan

# name, (x, y, w, h), kind
ELEMENTS: list[tuple] = [
    ("LOGO", (55, 60, 150, 95), "logo"),
    ("CAP", (265, 40, 115, 78), "cap"),
    ("SEAL", (95, 170, 450, 48), "seal"),
    ("LABEL", (105, 250, 430, 320), "label"),
    ("NETWT", (65, 650, 175, 60), "text"),
    ("BARCODE", (375, 610, 200, 120), "barcode"),
]


def _draw(img: np.ndarray, box, kind: str, name: str, *, angle=0.0,
          cap_color=(70, 90, 195), seal_broken=False) -> None:
    x, y, w, h = box
    layer = np.zeros_like(img)
    if kind == "logo":
        cv2.rectangle(layer, (x, y), (x + w, y + h), (60, 120, 205), -1)
        cv2.circle(layer, (x + 26, y + h // 2), 16, (245, 245, 245), -1)
        cv2.drawContours(
            layer, [np.array([(x + w - 45, y + 14), (x + w - 14, y + h - 14),
                              (x + w - 70, y + h - 14)])], -1, (245, 245, 245), -1
        )
    elif kind == "cap":
        cv2.rectangle(layer, (x, y), (x + w, y + h), cap_color, -1)
        cv2.rectangle(layer, (x, y), (x + w, y + h), tuple(int(c * 1.3) for c in cap_color), 3)
        cv2.line(layer, (x + 12, y + h // 2), (x + w - 12, y + h // 2), (30, 30, 30), 2)
    elif kind == "seal":
        end = x + (int(w * 0.4) if seal_broken else w)
        cv2.rectangle(layer, (x, y), (end, y + h), (60, 155, 195), -1)
        if seal_broken:
            for i in range(6):
                yy = y + int(i * h / 5)
                cv2.line(layer, (end, yy), (end + 12, yy + 4), (60, 155, 195), 2)
        else:
            for bx in range(x + 10, x + w, 26):
                cv2.line(layer, (bx, y + 4), (bx, y + h - 4), (40, 110, 150), 1)
    elif kind == "label":
        cv2.rectangle(layer, (x, y), (x + w, y + h), (248, 248, 248), -1)
        cv2.rectangle(layer, (x, y), (x + w, y + h), (120, 120, 120), 2)
        widths = [0.8, 0.55, 0.7, 0.4, 0.6]
        for i, frac in enumerate(widths):
            ly = y + 34 + i * 46
            cv2.rectangle(layer, (x + 24, ly), (x + 24 + int((w - 48) * frac), ly + 16),
                          (90, 90, 90), -1)
        cv2.rectangle(layer, (x + 24, y + h - 70), (x + w - 24, y + h - 26), (150, 170, 210), -1)
    elif kind == "barcode":
        cv2.rectangle(layer, (x, y), (x + w, y + h), (250, 250, 250), -1)
        rng = random.Random(7)
        bx = x + 12
        while bx < x + w - 12:
            bw = rng.choice([2, 2, 4, 6])
            cv2.rectangle(layer, (bx, y + 8), (bx + bw, y + h - 26), (20, 20, 20), -1)
            bx += bw + rng.choice([2, 3, 4])
        cv2.rectangle(layer, (x + 12, y + h - 22), (x + w - 12, y + h - 8), (20, 20, 20), 1)
    elif kind == "text":
        cv2.rectangle(layer, (x, y), (x + w, y + h), (240, 240, 240), -1)
        for i in range(2):
            cv2.rectangle(layer, (x + 10, y + 12 + i * 24),
                          (x + w - 14 - i * 30, y + 24 + i * 24), (90, 90, 90), -1)

    if angle:
        m = cv2.getRotationMatrix2D((x + w / 2, y + h / 2), angle, 1.0)
        layer = cv2.warpAffine(layer, m, (img.shape[1], img.shape[0]))
    mask = layer.any(axis=2)
    img[mask] = layer[mask]
    cv2.putText(img, name, (x, max(12, y - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.4,
                (70, 70, 70), 1, cv2.LINE_AA)


def render_box(skip=None, shift=None, rotate=None, *, cap_color=(70, 90, 195),
               seal_broken=False, seed=0) -> np.ndarray:
    rng = random.Random(seed)
    skip, shift, rotate = skip or set(), shift or {}, rotate or {}

    base = np.array(CARD, np.int16) + rng.randint(-5, 5)
    img = np.full((H, W, 3), np.clip(base, 0, 255).astype(np.uint8), np.uint8)
    # High-contrast carton edge + corner marks so stage-A quad detection has something
    # to lock onto (a real carton has a visible die-cut edge and print-registration marks).
    cv2.rectangle(img, (18, 18), (W - 18, H - 18), (70, 90, 120), 4)
    for cx, cy in [(34, 34), (W - 34, 34), (34, H - 34), (W - 34, H - 34)]:
        cv2.rectangle(img, (cx - 9, cy - 9), (cx + 9, cy + 9), (55, 65, 85), -1)
    cv2.line(img, (18, H // 2), (W - 18, H // 2), (120, 145, 170), 1)     # fold line
    for _ in range(60):  # kraft speckle / print texture
        px, py = rng.randint(40, W - 40), rng.randint(40, H - 40)
        cv2.circle(img, (px, py), 1, (135, 165, 190), -1)

    for name, box, kind in ELEMENTS:
        if name in skip:
            continue
        x, y, w, h = box
        dx, dy = shift.get(name, (0, 0))
        _draw(img, (x + dx, y + dy, w, h), kind, name,
              angle=rotate.get(name, 0.0),
              cap_color=cap_color if name == "CAP" else (70, 90, 195),
              seal_broken=seal_broken and name == "SEAL")

    yy, xx = np.mgrid[0:H, 0:W]
    r = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2)
    img = np.clip(img.astype(np.float32) * (1.0 - 0.16 * np.clip(r, 0, 1))[:, :, None],
                  0, 255).astype(np.uint8)
    noise = np.random.default_rng(seed).normal(0, 2, img.shape).astype(np.int16)
    return np.clip(img.astype(np.int16) + noise, 0, 255).astype(np.uint8)


def regions() -> list[Region]:
    spin = {"LABEL", "LOGO"}
    out = []
    for name, box, kind in ELEMENTS:
        tol = RegionTolerances(check_rotation=name in spin, position_tol_px=14.0)
        if kind == "barcode":
            # fine bar pattern aliases badly under perspective+resize; check
            # presence/position only, not fine visual match (that needs a decoder)
            tol.ssim_anomaly = 0.15
            tol.missing_corr = 0.3
        elif kind == "seal":
            tol.missing_corr = 0.3          # thin strip, partial occlusion by LOGO
        elif kind == "label":
            tol.ssim_anomaly = 0.55
        out.append(Region(name=name, bbox=box, expected_class=kind, tolerances=tol))
    return out


SCENES: list[tuple] = [
    ("good_01", "GOOD", dict(seed=2), dict(seed=201, angle=6), [], "clean carton"),
    ("good_02", "GOOD", dict(seed=5), dict(seed=202, angle=-7, scale=0.55), [], "smaller in frame"),
    ("defect_missing_cap", "DEFECTIVE", dict(skip={"CAP"}, seed=3), dict(seed=203, angle=4),
     ["CAP:MISSING_COMPONENT"], "cap absent"),
    ("defect_missing_label", "DEFECTIVE", dict(skip={"LABEL"}, seed=6), dict(seed=204, angle=-5),
     ["LABEL:MISSING_COMPONENT"], "label not applied"),
    ("defect_missing_barcode", "DEFECTIVE", dict(skip={"BARCODE"}, seed=8), dict(seed=205, angle=3),
     ["BARCODE:MISSING_COMPONENT"], "no barcode printed"),
    ("defect_shifted_label", "DEFECTIVE", dict(shift={"LABEL": (26, 18)}, seed=4),
     dict(seed=206, angle=4), ["LABEL:SHIFTED_COMPONENT"], "label misaligned"),
    ("defect_crooked_label", "DEFECTIVE", dict(rotate={"LABEL": 13.0}, seed=7),
     dict(seed=207, angle=-3), ["LABEL:ROTATED_COMPONENT"], "label applied crooked"),
    ("defect_seal_broken", "DEFECTIVE", dict(seal_broken=True, seed=9), dict(seed=208, angle=5),
     ["SEAL:MISSING_COMPONENT"], "tamper seal torn / not intact"),
    ("defect_wrong_cap_color", "DEFECTIVE", dict(cap_color=(70, 160, 70), seed=10),
     dict(seed=209, angle=-4), ["CAP:VISUAL_ANOMALY"], "wrong cap colour (green not red)"),
    ("review_blurred", "REVIEW", dict(seed=11), dict(seed=210, blur=15), [], "out of focus"),
    ("review_off_fixture", "REVIEW", dict(seed=12),
     dict(seed=211, angle=46, perspective=0.24, scale=0.30), [], "badly skewed / tiny"),
]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--activate", action="store_true", help="make BOX the active reference")
    args = ap.parse_args()

    cfg = get_settings()
    repo = ReferenceRepository(cfg)
    if args.force:
        try:
            repo.delete(REF_ID)
        except Exception:  # noqa: BLE001
            pass
    try:
        repo.get(REF_ID)
        print(f"reference {REF_ID} already exists (use --force to recreate)")
    except Exception:  # noqa: BLE001
        repo.create(
            ReferenceCreate(
                id=REF_ID, name="Demo Carton 001", kind=ProfileKind.BOX,
                regions=regions(), mm_per_px=0.20,
                notes="Synthetic printed-carton reference — proves the engine is profile-driven.",
            ),
            render_box(seed=1),
        )
        print(f"created reference {REF_ID}")
        if args.activate:
            repo.activate(REF_ID)
            print("activated BOX_MODEL_001")

    cases = [
        (name, photograph(render_box(**bkw), surface="mat", **pkw), label, expected, note)
        for name, label, bkw, pkw, expected, note in SCENES
    ]
    write_dataset(
        cfg.data_dir / "datasets" / "box_v1", "box_v1", REF_ID,
        "Simulated phone-camera photos of a printed carton. Smoke test, not a benchmark.",
        cases,
    )
    print("\nnext:")
    print("  py -m app.demo --image data/datasets/box_v1/images/defect_missing_cap.png "
          "--reference BOX_MODEL_001")
    print("  py scripts/run_dataset.py --dataset box_v1")


if __name__ == "__main__":
    main()
