"""Convert an external detection dataset to YOLO format under ``data/datasets/``.

Supported input layouts (``--format``):

  voc      Pascal VOC — a tree of *.xml (with <object><name>/<bndbox>) next to
           or alongside the images. Typical for assembled-PCB component sets
           such as PCB-SAID / PCB-AoI exports.
  coco     A single COCO-style annotations .json (+ an images dir).
  deeppcb  DeepPCB — group*/<id>_test.jpg with a <id>.txt of "x1 y1 x2 y2 cls"
           (cls 1..6). Produces a *defect* detector dataset.
  yolo     Already YOLO txt labels — just split + write data.yaml.

Output: data/datasets/<name>/{images/{train,val}, labels/{train,val}, data.yaml, classes.txt}

Examples
--------
  py scripts/prepare_dataset.py --format voc     --src data/raw/pcb_said   --name pcb_said_yolo
  py scripts/prepare_dataset.py --format deeppcb --src data/raw/deep_pcb   --name deeppcb_yolo
  py scripts/prepare_dataset.py --format coco    --src data/raw/set/ann.json --images data/raw/set/img --name set_yolo

No training happens here. See scripts/train_yolo.py.
"""

from __future__ import annotations

import argparse
import json
import random
import shutil
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

import _bootstrap  # noqa: F401
import cv2

from app.config import get_settings

IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp"}
DEEPPCB_CLASSES = ["open", "short", "mousebite", "spur", "copper", "pin-hole"]


def _img_size(path: Path) -> tuple[int, int]:
    im = cv2.imread(str(path))
    if im is None:
        raise ValueError(f"unreadable image: {path}")
    return im.shape[1], im.shape[0]  # w, h


def _yolo_line(cls: int, x1: float, y1: float, x2: float, y2: float, w: int, h: int) -> str:
    cx, cy = (x1 + x2) / 2 / w, (y1 + y2) / 2 / h
    bw, bh = abs(x2 - x1) / w, abs(y2 - y1) / h
    return f"{cls} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}"


# ---- parsers: return list[(image_path, [(cls_name, x1,y1,x2,y2), ...])] --------
def _parse_voc(src: Path) -> tuple[list, list[str]]:
    items, classes = [], []
    for xml in sorted(src.rglob("*.xml")):
        root = ET.parse(xml).getroot()
        stem = xml.stem
        img = next(
            (p for p in [xml.with_suffix(e) for e in IMG_EXT]
             + list(xml.parent.glob(stem + ".*"))
             + list((xml.parent.parent / "JPEGImages").glob(stem + ".*"))
             if p.suffix.lower() in IMG_EXT and p.is_file()),
            None,
        )
        if img is None:
            continue
        boxes = []
        for obj in root.findall("object"):
            name = (obj.findtext("name") or "").strip()
            bb = obj.find("bndbox")
            if not name or bb is None:
                continue
            boxes.append((name, float(bb.findtext("xmin")), float(bb.findtext("ymin")),
                          float(bb.findtext("xmax")), float(bb.findtext("ymax"))))
            classes.append(name)
        if boxes:
            items.append((img, boxes))
    return items, sorted(set(classes))


def _parse_coco(ann: Path, images_dir: Path) -> tuple[list, list[str]]:
    data = json.loads(ann.read_text("utf-8"))
    cats = {c["id"]: c["name"] for c in data["categories"]}
    imgs = {im["id"]: im for im in data["images"]}
    per_img: dict[int, list] = {}
    for a in data["annotations"]:
        x, y, w, h = a["bbox"]
        per_img.setdefault(a["image_id"], []).append(
            (cats[a["category_id"]], x, y, x + w, y + h)
        )
    items = []
    for iid, boxes in per_img.items():
        p = images_dir / imgs[iid]["file_name"]
        if p.is_file():
            items.append((p, boxes))
    return items, sorted(cats.values())


def _parse_deeppcb(src: Path) -> tuple[list, list[str]]:
    items = []
    for txt in sorted(src.rglob("*.txt")):
        if txt.name.lower() in {"trainval.txt", "test.txt", "train.txt"}:
            continue
        img = next((txt.with_name(txt.stem + s) for s in ("_test.jpg", ".jpg")
                    if (txt.with_name(txt.stem + s)).is_file()), None)
        if img is None:
            continue
        boxes = []
        for line in txt.read_text().splitlines():
            parts = line.split()
            if len(parts) >= 5:
                x1, y1, x2, y2, c = map(float, parts[:5])
                boxes.append((DEEPPCB_CLASSES[int(c) - 1], x1, y1, x2, y2))
        if boxes:
            items.append((img, boxes))
    return items, DEEPPCB_CLASSES


def _parse_yolo(src: Path) -> tuple[list, list[str]]:
    names_file = next((p for p in src.rglob("*.yaml")), None) or next(
        (p for p in src.rglob("classes.txt")), None
    )
    classes: list[str] = []
    if names_file and names_file.suffix == ".txt":
        classes = names_file.read_text().split()
    items = []
    for lbl in sorted(src.rglob("*.txt")):
        if lbl.name == "classes.txt":
            continue
        img = next((lbl.with_suffix(e) for e in IMG_EXT if lbl.with_suffix(e).is_file()), None)
        if img:
            items.append((img, lbl))  # passthrough label file
    return items, classes


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--format", required=True, choices=["voc", "coco", "deeppcb", "yolo"])
    ap.add_argument("--src", required=True, type=Path, help="dataset root (or COCO json)")
    ap.add_argument("--images", type=Path, help="images dir (COCO only)")
    ap.add_argument("--name", required=True, help="output dataset name under data/datasets/")
    ap.add_argument("--val-frac", type=float, default=0.2)
    ap.add_argument("--class-map", type=Path, help="optional JSON {src_class: canonical}")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    if not args.src.exists():
        raise SystemExit(f"--src not found: {args.src}\nSee data/raw/README.md for where to unzip datasets.")

    cmap = json.loads(args.class_map.read_text("utf-8")) if args.class_map else {}

    if args.format == "voc":
        items, classes = _parse_voc(args.src)
    elif args.format == "coco":
        if not args.images:
            raise SystemExit("--images is required for --format coco")
        items, classes = _parse_coco(args.src, args.images)
    elif args.format == "deeppcb":
        items, classes = _parse_deeppcb(args.src)
    else:
        items, classes = _parse_yolo(args.src)

    if cmap:
        classes = sorted({cmap.get(c, c) for c in classes})
    if not items:
        raise SystemExit("no (image, annotation) pairs found — check --format and --src layout")

    cls_idx = {c: i for i, c in enumerate(classes)}
    out = get_settings().data_dir / "datasets" / args.name
    for sub in ("images/train", "images/val", "labels/train", "labels/val"):
        (out / sub).mkdir(parents=True, exist_ok=True)

    rng = random.Random(args.seed)
    rng.shuffle(items)
    n_val = int(len(items) * args.val_frac)
    counts: Counter = Counter()

    for i, (img, ann) in enumerate(items):
        split = "val" if i < n_val else "train"
        dst_img = out / "images" / split / img.name
        shutil.copy(img, dst_img)
        lbl_path = out / "labels" / split / (img.stem + ".txt")

        if args.format == "yolo":
            shutil.copy(ann, lbl_path)  # ann is the label file
            continue

        w, h = _img_size(img)
        lines = []
        for name, x1, y1, x2, y2 in ann:
            canon = cmap.get(name, name)
            if canon not in cls_idx:
                continue
            lines.append(_yolo_line(cls_idx[canon], x1, y1, x2, y2, w, h))
            counts[canon] += 1
        lbl_path.write_text("\n".join(lines), "utf-8")

    (out / "classes.txt").write_text("\n".join(classes), "utf-8")
    (out / "data.yaml").write_text(
        f"# generated by prepare_dataset.py from {args.src}\n"
        f"path: {out.as_posix()}\n"
        f"train: images/train\nval: images/val\n"
        f"nc: {len(classes)}\n"
        f"names: {classes}\n",
        "utf-8",
    )

    print(f"wrote {out}")
    print(f"  images: {len(items) - n_val} train / {n_val} val")
    print(f"  classes ({len(classes)}): {classes}")
    if counts:
        print("  instances:", dict(counts))
    print(f"\ntrain:  py scripts/train_yolo.py --data {(out / 'data.yaml').as_posix()}")


if __name__ == "__main__":
    main()
