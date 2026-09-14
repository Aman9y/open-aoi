"""Shared scene synthesis for the demo datasets (PCB, box, ...).

`photograph()` composites a flat rendered object into a realistic off-axis
"phone photo" — cluttered surface, placement, rotation, mild perspective, glare,
shadow, sensor noise — so stage-A board/object detection has real work to do.

This is test-data generation. The inspection engine runs for real on the output.
"""

from __future__ import annotations

import json

import cv2
import numpy as np


def perturb(img: np.ndarray, tx: float = 0, ty: float = 0, angle: float = 0.0,
            blur: int = 0, border: tuple[int, int, int] = (127, 127, 127)) -> np.ndarray:
    """Small in-frame affine wobble — used by unit tests for precise control."""
    h, w = img.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    m[0, 2] += tx
    m[1, 2] += ty
    out = cv2.warpAffine(img, m, (w, h), borderValue=border)
    if blur:
        out = cv2.GaussianBlur(out, (blur | 1, blur | 1), 0)
    return out


_SURFACES = {
    "desk": ((150, 165, 185), (138, 152, 172)),   # pale wood
    "mat": ((78, 82, 92), (70, 74, 84)),          # dark inspection mat
}


def desk_background(rng: np.random.Generator, sh: int, sw: int,
                    surface: str = "desk") -> np.ndarray:
    base, grain = _SURFACES.get(surface, _SURFACES["desk"])
    bg = np.zeros((sh, sw, 3), np.uint8)
    bg[:] = base
    for _ in range(140):  # surface grain
        y = int(rng.integers(0, sh))
        cv2.line(bg, (0, y), (sw, y + int(rng.integers(-6, 6))), grain, 1)
    for _ in range(6):  # clutter
        x, y = int(rng.integers(0, sw)), int(rng.integers(0, sh))
        col = tuple(int(c) for c in rng.integers(25, 95, 3))
        cv2.rectangle(bg, (x, y), (x + int(rng.integers(40, 160)),
                                   y + int(rng.integers(20, 90))), col, -1)
    noise = rng.normal(0, 4, bg.shape).astype(np.int16)
    return np.clip(bg.astype(np.int16) + noise, 0, 255).astype(np.uint8)


def photograph(flat: np.ndarray, seed: int, *, scale: float = 0.62, angle: float = 7.0,
               perspective: float = 0.05, glare: float = 55.0, blur: int = 0,
               surface: str = "desk", out_long: int = 1280) -> np.ndarray:
    rng = np.random.default_rng(seed)
    sh, sw = 1000, 1400
    bg = desk_background(rng, sh, sw, surface)

    bh, bw = flat.shape[:2]
    s = scale * min(sh / bh, sw / bw)
    resized = cv2.resize(flat, (int(bw * s), int(bh * s)))
    rh, rw = resized.shape[:2]

    a = abs(angle)
    th = np.radians(rng.uniform(-a, a))
    rot = np.array([[np.cos(th), -np.sin(th)], [np.sin(th), np.cos(th)]])
    corners = np.array([[-rw / 2, -rh / 2], [rw / 2, -rh / 2],
                        [rw / 2, rh / 2], [-rw / 2, rh / 2]]) @ rot.T
    corners += rng.uniform(-perspective, perspective, corners.shape) * np.array([rw, rh])
    cx = rng.uniform(rw * 0.6, sw - rw * 0.6)
    cy = rng.uniform(rh * 0.6, sh - rh * 0.6)
    dst = (corners + np.array([cx, cy])).astype(np.float32)
    src = np.array([[0, 0], [rw, 0], [rw, rh], [0, rh]], np.float32)

    mat = cv2.getPerspectiveTransform(src, dst)
    warped = cv2.warpPerspective(resized, mat, (sw, sh))
    mask = cv2.warpPerspective(np.full((rh, rw), 255, np.uint8), mat, (sw, sh))

    shadow = cv2.GaussianBlur(mask, (61, 61), 0).astype(np.float32) / 255.0
    bg = (bg.astype(np.float32) * (1.0 - 0.35 * shadow[:, :, None])).astype(np.uint8)
    bg[mask > 0] = warped[mask > 0]

    if glare > 0:
        gl = np.zeros((sh, sw), np.float32)
        cv2.circle(gl, (int(rng.integers(0, sw)), int(rng.integers(0, sh))),
                   int(rng.integers(140, 240)), 1.0, -1)
        gl = cv2.GaussianBlur(gl, (0, 0), 90)
        bg = np.clip(bg.astype(np.float32) + gl[:, :, None] * glare, 0, 255).astype(np.uint8)

    yy, xx = np.mgrid[0:sh, 0:sw]
    rad = np.sqrt(((xx - sw / 2) / (sw / 2)) ** 2 + ((yy - sh / 2) / (sh / 2)) ** 2)
    bg = np.clip(bg.astype(np.float32) * (1.0 - 0.22 * np.clip(rad, 0, 1))[:, :, None],
                 0, 255).astype(np.uint8)
    bg = np.clip(bg.astype(np.int16) + rng.normal(0, 3, bg.shape).astype(np.int16),
                 0, 255).astype(np.uint8)
    if blur:
        bg = cv2.GaussianBlur(bg, (blur | 1, blur | 1), 0)

    k = out_long / max(sh, sw)
    return cv2.resize(bg, (int(sw * k), int(sh * k)), interpolation=cv2.INTER_AREA)


def write_dataset(ds_dir, name: str, reference_id: str, note: str,
                  cases: list[tuple]) -> None:
    """cases: list of (filename, image, label, expected_defects, case_note)."""
    img_dir = ds_dir / "images"
    img_dir.mkdir(parents=True, exist_ok=True)
    manifest = {"dataset": name, "reference_id": reference_id, "source": "synthetic",
                "note": note, "images": []}
    for fname, img, label, expected, cnote in cases:
        cv2.imwrite(str(img_dir / f"{fname}.png"), img)
        manifest["images"].append(
            {"file": f"images/{fname}.png", "label": label,
             "expected_defects": expected, "note": cnote, "source": "synthetic"}
        )
        print(f"  wrote images/{fname}.png  [{label}]")
    (ds_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), "utf-8")
    print(f"\nmanifest: {ds_dir / 'manifest.json'}  ({len(cases)} images)")
