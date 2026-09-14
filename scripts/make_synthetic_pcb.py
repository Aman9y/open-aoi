"""Generate the known-good PCB reference + a labelled dataset of simulated
phone-camera photos (``data/datasets/synthetic_v1/``).

This is **test-data generation**, not a fake predictor: the inspection engine runs
for real on every image produced here. It exists so the whole pipeline is
demonstrable with zero hardware. Add real camera photos later by creating
``data/datasets/<name>/images/`` + a ``manifest.json`` — no pipeline changes.

    py scripts/make_synthetic_pcb.py [--force]
"""

from __future__ import annotations

import argparse
import json
import random

import _bootstrap  # noqa: F401  (sys.path shim)
import cv2
import numpy as np

from app.config import get_settings
from app.schemas.reference import ProfileKind, Region, RegionTolerances, ReferenceCreate
from app.storage.reference_repository import ReferenceRepository

REF_ID = "PCB_MODEL_001"
W, H = 900, 640
BOARD_GREEN = (60, 120, 45)

# name, (x, y, w, h), kind
COMPONENTS: list[tuple[str, tuple[int, int, int, int], str]] = [
    ("IC1", (120, 110, 150, 110), "ic"),
    ("IC2", (520, 90, 120, 90), "ic"),
    ("R1", (110, 300, 70, 26), "resistor"),
    ("R2", (110, 350, 70, 26), "resistor"),
    ("R3", (110, 400, 70, 26), "resistor"),
    ("R17", (330, 470, 26, 70), "resistor"),
    ("C1", (300, 300, 46, 46), "cap"),
    ("C4", (380, 300, 46, 46), "cap"),
    ("C7", (460, 300, 46, 46), "cap"),
    ("LED1", (700, 300, 40, 40), "led"),
    ("J1", (680, 460, 160, 80), "connector"),
]


def _draw_component(img: np.ndarray, box: tuple[int, int, int, int], kind: str,
                    name: str, angle: float = 0.0) -> None:
    x, y, w, h = box
    layer = np.zeros_like(img)
    if kind == "ic":
        cv2.rectangle(layer, (x, y), (x + w, y + h), (35, 35, 35), -1)
        cv2.rectangle(layer, (x, y), (x + w, y + h), (90, 90, 90), 2)
        for i in range(6):
            px = x + 12 + i * (w - 24) // 5
            cv2.rectangle(layer, (px - 3, y - 6), (px + 3, y), (180, 180, 180), -1)
            cv2.rectangle(layer, (px - 3, y + h), (px + 3, y + h + 6), (180, 180, 180), -1)
        cv2.circle(layer, (x + 14, y + 14), 4, (200, 200, 200), -1)
    elif kind == "resistor":
        cv2.rectangle(layer, (x, y), (x + w, y + h), (40, 50, 130), -1)
        for i in range(3):
            if w > h:
                bx = x + 12 + i * 14
                cv2.line(layer, (bx, y + 2), (bx, y + h - 2), (20, 20, 20), 2)
            else:
                by = y + 12 + i * 14
                cv2.line(layer, (x + 2, by), (x + w - 2, by), (20, 20, 20), 2)
    elif kind == "cap":
        cv2.rectangle(layer, (x, y), (x + w, y + h), (110, 140, 190), -1)
        cv2.rectangle(layer, (x, y), (x + w, y + h), (60, 80, 120), 2)
    elif kind == "led":
        cv2.circle(layer, (x + w // 2, y + h // 2), w // 2, (60, 60, 210), -1)
        cv2.circle(layer, (x + w // 2, y + h // 2), w // 2, (180, 180, 220), 1)
    elif kind == "connector":
        cv2.rectangle(layer, (x, y), (x + w, y + h), (20, 20, 20), -1)
        for i in range(6):
            cx = x + 14 + i * (w - 28) // 5
            cv2.circle(layer, (cx, y + h // 2), 6, (170, 150, 60), -1)

    if angle:
        M = cv2.getRotationMatrix2D((x + w / 2, y + h / 2), angle, 1.0)
        layer = cv2.warpAffine(layer, M, (img.shape[1], img.shape[0]))

    mask = layer.any(axis=2)
    img[mask] = layer[mask]
    cv2.putText(img, name, (x, max(12, y - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.4,
               (230, 230, 230), 1, cv2.LINE_AA)


def render_board(skip: set[str] | None = None, shift: dict[str, tuple[int, int]] | None = None,
                 rotate: dict[str, float] | None = None, seed: int = 0) -> np.ndarray:
    rng = random.Random(seed)
    skip = skip or set()
    shift = shift or {}
    rotate = rotate or {}

    base = np.array(BOARD_GREEN, np.int16) + rng.randint(-4, 4)
    img = np.full((H, W, 3), np.clip(base, 0, 255).astype(np.uint8), np.uint8)
    cv2.rectangle(img, (30, 30), (W - 30, H - 30), (90, 160, 70), 3)
    for (cx, cy) in [(55, 55), (W - 55, 55), (55, H - 55), (W - 55, H - 55)]:
        cv2.circle(img, (cx, cy), 12, (200, 200, 190), -1)   # fiducials / mount holes
        cv2.circle(img, (cx, cy), 5, (40, 40, 40), -1)
    for _ in range(40):  # silkscreen traces for feature richness
        p1 = (rng.randint(40, W - 40), rng.randint(40, H - 40))
        p2 = (p1[0] + rng.randint(-60, 60), p1[1] + rng.randint(-60, 60))
        cv2.line(img, p1, p2, (95, 150, 80), 1)

    for name, box, kind in COMPONENTS:
        if name in skip:
            continue
        x, y, w, h = box
        dx, dy = shift.get(name, (0, 0))
        _draw_component(img, (x + dx, y + dy, w, h), kind, name, rotate.get(name, 0.0))

    # Soft lighting vignette (mimics an LED ring / dome light on the fixture).
    yy, xx = np.mgrid[0:H, 0:W]
    r = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2)
    vign = (1.0 - 0.18 * np.clip(r, 0, 1))[:, :, None]
    img = np.clip(img.astype(np.float32) * vign, 0, 255).astype(np.uint8)

    noise = np.random.default_rng(seed).normal(0, 2, img.shape).astype(np.int16)
    return np.clip(img.astype(np.int16) + noise, 0, 255).astype(np.uint8)


# scene synthesis (desk background, perspective photo, affine wobble) is shared
from _scene import perturb, photograph, write_dataset  # noqa: E402

_ = (perturb, photograph)  # re-exported for scripts/tests



def regions() -> list[Region]:
    out: list[Region] = []
    for name, box, kind in COMPONENTS:
        tol = RegionTolerances(check_rotation=(kind != "led"))
        if kind == "connector":
            tol.position_tol_px = 12.0
        out.append(Region(name=name, bbox=box, expected_class=kind, tolerances=tol))
    return out


DATASET = "synthetic_v1"

# name -> (label, board kwargs, photograph kwargs, expected_defects, note)
SCENES: list[tuple] = [
    ("good_01", "GOOD", dict(seed=2), dict(seed=101, angle=6), [], "clean board, slight angle"),
    ("good_02", "GOOD", dict(seed=7), dict(seed=102, angle=-8, scale=0.55), [], "smaller in frame"),
    ("good_03", "GOOD", dict(seed=12), dict(seed=103, angle=3, glare=75), [], "stronger glare"),
    ("defect_missing_R17", "DEFECTIVE", dict(skip={"R17"}, seed=3), dict(seed=104, angle=5),
     ["R17:MISSING_COMPONENT"], "resistor R17 not placed"),
    ("defect_missing_C4", "DEFECTIVE", dict(skip={"C4"}, seed=8), dict(seed=105, angle=-6),
     ["C4:MISSING_COMPONENT"], "capacitor C4 not placed"),
    ("defect_shifted_C4", "DEFECTIVE", dict(shift={"C4": (22, 14)}, seed=4), dict(seed=106, angle=4),
     ["C4:SHIFTED_COMPONENT"], "C4 offset ~26px"),
    ("defect_rotated_IC2", "DEFECTIVE", dict(rotate={"IC2": 18.0}, seed=5), dict(seed=107, angle=-3),
     ["IC2:ROTATED_COMPONENT"], "IC2 rotated 18 deg"),
    ("defect_multi", "DEFECTIVE",
     dict(skip={"R3"}, shift={"C7": (18, -16)}, rotate={"IC1": 12.0}, seed=9),
     dict(seed=108, angle=6), ["R3:MISSING_COMPONENT", "C7:SHIFTED_COMPONENT", "IC1:ROTATED_COMPONENT"],
     "three simultaneous defects"),
    ("review_blurred", "REVIEW", dict(seed=6), dict(seed=109, blur=15),
     [], "camera out of focus -> REVIEW"),
    ("review_off_fixture", "REVIEW", dict(seed=10),
     dict(seed=110, angle=46, perspective=0.24, scale=0.30),
     [], "board badly skewed / tiny -> alignment should refuse"),
]


def _make_reference(repo: ReferenceRepository, force: bool) -> None:
    if force:
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
                id=REF_ID, name="Demo PCB Model 001", kind=ProfileKind.PCB,
                regions=regions(), mm_per_px=0.12,
                notes="Synthetic rectified known-good board for the hardware-free demo.",
            ),
            render_board(seed=1),  # reference = clean, tightly framed (as captured in a fixture)
        )
        repo.activate(REF_ID)
        print(f"created + activated reference {REF_ID}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true", help="recreate reference if it exists")
    args = ap.parse_args()

    cfg = get_settings()
    repo = ReferenceRepository(cfg)
    _make_reference(repo, args.force)

    cases = [
        (name, photograph(render_board(**bkw), **pkw), label, expected, note)
        for name, label, bkw, pkw, expected, note in SCENES
    ]
    write_dataset(
        cfg.data_dir / "datasets" / DATASET, DATASET, REF_ID,
        "Simulated phone-camera photos of a synthetic PCB. Smoke test, not a benchmark.",
        cases,
    )
    print("\nnext:")
    print(f"  py -m app.demo --image data/datasets/{DATASET}/images/defect_multi.png")
    print(f"  py scripts/run_dataset.py --dataset {DATASET}")


if __name__ == "__main__":
    main()
