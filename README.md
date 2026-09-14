# AI-Assisted Visual Quality Inspection

A low-cost, camera-based inspection station that examines an assembled product and
returns **GOOD / DEFECTIVE / REVIEW** — and, for defects, shows an operator
*exactly where and why*.

> **This is a prototype.** It is not certified for manufacturing use and makes no
> claim of production readiness.

The first target is **assembled PCB inspection**, built as a simplified
[Automated Optical Inspection (AOI)](https://en.wikipedia.org/wiki/Automated_optical_inspection)
pipeline. The engine is **profile-driven**: a second profile — a **printed carton
/ box** (`BOX_MODEL_001`) — runs through the exact same detect → align → compare →
decide pipeline with zero product-specific code, proving the platform is not
hardwired to PCBs.

---

## The product principle

Not *"AI says this board is defective (97%)."*

But *"Component R17 is missing, C4 is 1.8 mm out of position (tolerance 0.75 mm),
and IC2 is rotated 18°. Here is the annotated image."*

Explainability and reliability over model complexity.

---

## Real-world motivation

Electronics assembly lines use AOI machines costing tens of thousands of dollars
to catch missing, misplaced, mis-oriented and mis-soldered components before a
board ships. This project reproduces the **core deterministic logic** of such a
system — capture → detect → align to a known-good reference → inspect regions →
decide → localize — on a webcam / phone-camera budget, with a clean extension path
to learned models.

---

## How it works

```
image ─▶ detect + rectify board ─▶ quality gate ─▶ align to reference (ORB → ECC)
      ─▶ per-region compare (template match + rotation sweep · ECC angle · SSIM)
      ─▶ typed defects (missing / shifted / rotated / anomaly)
      ─▶ decision engine (+ registration-trust guard)
      ─▶ GOOD / DEFECTIVE / REVIEW  + annotated image + montage + JSON
```

| Task | Tool |
|---|---|
| preprocessing, board detection, alignment, geometry, difference images | **OpenCV** |
| component class ID → catches **wrong part placed**; corroborates missing/present *(optional)* | **YOLO** |
| combining evidence, tolerances, explainable verdict | **decision engine** |
| visual anomaly *(pluggable — PatchCore / EfficientAD later)* | reference SSIM/diff now |

The deterministic pipeline is the product. YOLO is **additive and never a hard
dependency**: it runs only if `AOI_YOLO_MODEL_PATH` points at a real model, it
adds a `WRONG_COMPONENT` check and present/missing corroboration, and it never
overrides a clean deterministic verdict. With no model the system reports
`MODEL NOT CONFIGURED` and still produces the deterministic result — it does not
fake inference.

Safety property, enforced and tested: **uncertain input never becomes GOOD.**
Failed alignment, poor image quality, or low confidence → `REVIEW`.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the module map and stage-by-stage detail.

---

## Quick start

```bash
python -m venv .venv && .venv\Scripts\activate        # Windows
pip install -r backend/requirements.txt

# demo references + labelled datasets of simulated phone-camera photos (no hardware)
python scripts/make_synthetic_pcb.py     # PCB_MODEL_001  + data/datasets/synthetic_v1
python scripts/make_synthetic_box.py     # BOX_MODEL_001  + data/datasets/box_v1

cd backend
python -m app.demo --image ../data/datasets/synthetic_v1/images/defect_multi.png
python -m app.demo --image ../data/datasets/box_v1/images/defect_missing_cap.png \
                   --reference BOX_MODEL_001
```

```
========================================================
 INSPECTION RESULT   [ DEFECTIVE ]
========================================================
 reference    : PCB_MODEL_001 (PCB)
 confidence   : 0.94      time : 480 ms
 board detect : found=True method=quad coverage=0.37
 alignment    : success=True err=0.9px rot=-0.1deg inliers=210
 board match  : SSIM 0.91

 3 component defect(s) beyond tolerance:
   IC1 (rotated component), R3 (missing component), C7 (shifted component).

 DEFECTS (3):
   - IC1    ROTATED_COMPONENT    77.0%   observed: Rotated +12.0 deg
   - R3     MISSING_COMPONENT    84.0%   observed: No matching component detected
   - C7     SHIFTED_COMPONENT    99.0%   observed: offset 24.1px (allowed 8.0px)
========================================================
```

Run the whole dataset (original / cropped / aligned / annotated / montage / JSON per
image, plus a summary table and contact sheet):

```bash
python scripts/run_dataset.py --dataset synthetic_v1
# -> outputs/datasets/synthetic_v1/{summary.md, summary.csv, contact_sheet.png, <name>/}
```

Then the dashboard:

```bash
# terminal 1
cd backend && python -m uvicorn app.main:app --port 8000
# terminal 2
cd frontend && npm install && npm run dev      # http://localhost:5173
```

Full instructions incl. camera/phone setup: [SETUP.md](SETUP.md).

---

## Dashboard

Operator-station layout: top status bar (active reference · model · system state),
left nav, and a work area per page.

| Page | What it does |
|---|---|
| **Inspect** | pick a product (PCB or box) → **upload / webcam / stream URL** → full-width GOOD/DEFECTIVE/REVIEW verdict banner, annotated image (annotated / original / cropped / aligned tabs), explainable defect cards, confidence + timing + alignment metrics |
| **History** | every inspection, filter by result/date, open annotated detail, export CSV |
| **Analytics** | GOOD/DEFECTIVE/REVIEW counts, defect rate, reason distribution, avg time |
| **References** | manage known-good references (any profile kind), regions & tolerances, set the active reference, auto-detect regions (needs YOLO) |

---

## Creating a reference board

1. Capture a known-good board under your production lighting/fixture.
2. **References → Add reference**: give it an id (`PCB_MODEL_002`), a name, upload
   the image, mark it active.
3. Define inspection regions in its `data/references/<id>/regions.json` (or via
   the regions field in the form):

```json
[
  { "name": "R17", "bbox": [330, 470, 26, 70],
    "tolerances": { "position_tol_px": 8, "rotation_tol_deg": 8 } },
  { "name": "LED1", "bbox": [700, 300, 40, 40],
    "tolerances": { "check_rotation": false } }
]
```

Tolerances left unset fall back to global config. Nothing is hard-coded in the app.

`kind` (`PCB` / `BOX` / `GENERIC`) is a label only — the engine branches on
`inspection_mode`, never on kind:

- **`regions`** (default) — per-component checks: missing / shifted / rotated /
  wrong-part / colour, against the region list above.
- **`surface`** — whole-object "does it match the known-good reference?". No
  regions needed. A scratched / dirty / mis-printed / wrong / damaged object
  shows up as a large surface difference → `DEFECTIVE`. Use this for a custom demo
  object: **References → Capture from camera → mode: Whole surface**, snapshot a
  clean one, then a clean object reads GOOD and a damaged one reads DEFECTIVE.

### A different product — the box profile

`scripts/make_synthetic_box.py` creates `BOX_MODEL_001` (a printed carton) and
`data/datasets/box_v1/`. It exercises the **same** pipeline on a completely
different object:

```bash
python scripts/make_synthetic_box.py
python scripts/run_dataset.py --dataset box_v1     # 11/11, localization 1.0, 0 false accepts
python -m app.demo --image data/datasets/box_v1/images/defect_wrong_cap_color.png \
                   --reference BOX_MODEL_001
```

Box defects covered: missing cap / label / barcode, shifted label, crooked
(rotated) label, torn tamper seal, wrong cap colour, out-of-focus, off-fixture.
Colour defects are caught by a per-region CIELAB check (grayscale template
matching alone would miss a green cap where a red one belongs).

---

## Inspecting an image / using a camera

**Dashboard — Inspect page**, three input modes:

| Mode | Use for | How |
|---|---|---|
| Upload image | a phone photo or saved file | drag-drop / browse |
| Webcam | any camera the browser sees (USB webcam, phone via iVCam / EpocCam / Phone Link) | live `<video>` preview, frame grabbed in-browser |
| Stream URL | a phone running an IP-webcam app, or a local device index | paste `http://<phone-ip>:8080/video` (or click a detected `Camera N`), backend grabs the frame |

Webcam and Stream modes both have a **Start live inspection** button: the station
re-inspects the feed every ~2 s and shows a rolling GOOD / DEFECTIVE / REVIEW
(these frames are *not* saved). **Record this frame** saves the current result to
history. **Capture & inspect** runs and saves a single frame.

**Multi-camera** mode inspects one object from 2–4 cameras at once (e.g. front ·
top · back), each against its own reference; the verdict is the **worst view**
and defects are reported per view. `POST /api/inspections/inspect_multi`.

**CLI:**

```bash
python -m app.demo --image path/to.jpg
python -m app.demo --camera 0
python -m app.demo --stream http://<phone-ip>:8080/video
python scripts/probe_camera.py --list          # find local camera indices
python scripts/probe_camera.py --stream <url>   # test a phone stream before inspecting
```

**API:** `POST /api/inspections/inspect` (multipart), `POST /api/inspections/inspect_live`
(`{source, reference_id}` — `source` is a device index or stream URL),
`GET /api/camera/devices`, `GET /api/camera/preview?source=…` (MJPEG).

The `ImageSource` abstraction (`FileSource` / `UploadSource` / `CameraSource` /
`StreamSource`) and a shared `CameraHub` (one capture per source, read by both the
preview and the snapshot) keep capture decoupled from the engine. Phone-camera
setup details: [SETUP.md](SETUP.md).

---

## Evaluation

```bash
python scripts/evaluate.py --dataset synthetic_v1
```

Reads the dataset manifest, runs the engine for real on every image, and reports
accuracy, precision, recall, F1, false-positive / false-negative rate, defect
localization, average time, and — highlighted separately — **FALSE ACCEPTS** (a
defective board classified GOOD), the critical error class. Writes
`outputs/eval/<dataset>/report.md`.

> The bundled `synthetic_v1` dataset is **simulated** (rendered board composited
> into a photo-like scene) and self-consistent, so it is a pipeline smoke test,
> **not a performance claim**. Real numbers require images captured from the
> physical rig and a held-out split. No accuracy is claimed until that evaluation
> is run.

---

## Datasets

Datasets live under `data/datasets/<name>/` with a `manifest.json`:

```json
{ "dataset": "synthetic_v1", "reference_id": "PCB_MODEL_001",
  "images": [
    { "file": "images/defect_multi.png", "label": "DEFECTIVE",
      "expected_defects": ["R3:MISSING_COMPONENT", "C7:SHIFTED_COMPONENT"],
      "note": "three simultaneous defects", "source": "synthetic" }
  ] }
```

`run_dataset.py` and `evaluate.py` both read this manifest; without one they fall
back to filename-prefix labels (`good_*` / `defect_*` / `review_*`). To add **real
camera photos**: capture images, drop them in `data/datasets/camera_v1/images/`,
write a `manifest.json`, and run the same commands — no pipeline changes.

External detection datasets for training the optional YOLO detector go under
`data/raw/` — **exact placement and conversion commands: [data/raw/README.md](data/raw/README.md)**.

| Dataset | Purpose | Location |
|---|---|---|
| our own camera captures | **final validation** (the one that matters) | `data/datasets/camera_v1/` |
| PCB-SAID | assembled-SMD component detection (YOLO training) | `data/raw/pcb_said/` |
| DeepPCB | bare-board trace defects; reference-vs-test dev | `data/raw/deep_pcb/` |
| MVTec AD / AD 2 | anomaly-detection experiments (future) | `data/raw/mvtec/` |

---

## Component detector (optional YOLO)

The deterministic pipeline needs no model. To add class-level checks:

```bash
pip install -r backend/requirements-ml.txt          # ~1-2 GB (PyTorch)

# 1. convert a dataset to YOLO format  (see data/raw/README.md)
python scripts/prepare_dataset.py --format voc --src data/raw/pcb_said --name pcb_said_yolo

# 2. train  (outside the web server)
python scripts/train_yolo.py --data data/datasets/pcb_said_yolo/data.yaml

# 3. evaluate on the held-out split  — the ONLY source of a real mAP number
python scripts/eval_detector.py --data data/datasets/pcb_said_yolo/data.yaml \
                                --weights models/component_detector.pt

# 4. enable
export AOI_YOLO_MODEL_PATH=models/component_detector.pt
```

**A pretrained model works with no training** — download a PCB-component YOLO
`.pt` from Roboflow Universe or Hugging Face, drop it at
`models/component_detector.pt`, then:

```bash
export AOI_YOLO_MODEL_PATH=models/component_detector.pt
python scripts/check_model.py --image data/datasets/synthetic_v1/images/good_01.png
```

`check_model.py` prints the model's class names, runs a test inference, and
suggests an `AOI_YOLO_CLASS_ALIASES` mapping so the detector's vocabulary lines up
with each reference's `expected_class` (resistor / cap / ic / led / connector).
Still run the held-out eval (step 3) before quoting a number.

With a model loaded, inspections gain a `WRONG_COMPONENT` check and per-region
detector agreement, `model_status` becomes `YOLO_ACTIVE`, and the annotated image
shows detection boxes. **References → auto-detect regions** proposes inspection
regions for a new board from the detector. No model → `MODEL NOT CONFIGURED`,
deterministic result unchanged.

---

## Physical station (optional — ESP32)

Turn the software into a bench station. An **ESP32 over Wi-Fi** drives a
green/red/amber lamp stack, a **servo reject gate**, and a buzzer; a button (or a
part-present sensor) triggers an inspection.

```
 phone camera ─▶ laptop (backend + dashboard)
                     ▲            │
       POST /trigger │            │ GET /state  (poll ~2.5 Hz)
                     │            ▼
                  ESP32 ─▶ LED stack + servo reject gate + buzzer
                    └──◀── button / part-present sensor
```

```bash
cd backend && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
# .env:
AOI_STATION_ENABLED=true
AOI_STATION_SOURCE=http://192.168.1.42:8080/video
```

Flash `hardware/inspection_station/`, set your Wi-Fi + the laptop IP. Every
inspection (station button, dashboard upload, live camera) updates the lamp
stack; a `DEFECTIVE` verdict fires the reject servo and the run is saved to
History. Full wiring + setup: **[hardware/README.md](hardware/README.md)**.

The dashboard **Inspect** page shows a **Station** card (connection status + a
"Trigger inspection" button) whenever the station is enabled.

---

## Testing

```bash
python -m pytest tests/ -q
```

41 tests: alignment (translation / rotation / failure), component inspection
(present / missing / shifted / rotated), colour anomaly, the decision-engine truth
table, board detection, YOLO fusion (scripted fake detector), the box profile,
the camera + station endpoints, and the API.

---

## Limitations

- No component detector or anomaly model **ships**. The YOLO integration is wired
  and tested but inert until you train a model (`backend/requirements-ml.txt` +
  `scripts/`). No anomaly model yet (interface in place — `models/anomaly_detector.py`).
- Board detection handles a board on a cluttered surface at a moderate angle; a
  board rotated ~90°, badly skewed, or the same colour as its background may not
  be found — the frame then passes through and alignment becomes the gate.
- Alignment assumes a mostly top-down view. Severe misframing → `REVIEW`.
- Quality and tolerance thresholds ship with prototype defaults tuned for the
  simulated dataset and **must be calibrated** to a real camera + lighting rig.
- No white-balance / exposure normalization yet — real sensors vary more than the
  simulated set.
- Single reference per inspection; no multi-angle or conveyor integration.
- Confidence values are calibrated heuristics derived from measured margins, not
  model probabilities (documented in `defect_detector.py`).
- Bundled dataset is simulated, not real photographs.

## Future improvements

Train + ship a component detector · PatchCore / EfficientAD anomaly detection ·
solder-joint checks · barcode/OCR verification · multi-angle capture · real
conveyor + multi-bin sorting · human-review feedback loop · production analytics ·
object-storage backend.

These exist as extension points only; see [ARCHITECTURE.md](ARCHITECTURE.md) §7.
