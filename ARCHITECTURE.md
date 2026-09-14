# ARCHITECTURE

AI-Assisted Visual Quality Inspection — a simplified, explainable Automated Optical
Inspection (AOI) station. The first target product is **assembled PCB inspection**;
the engine is profile-driven so other rigid objects (e.g. a printed carton / box)
can be added without touching the pipeline.

> Status: **prototype**. Not production hardened, not certified for manufacturing use.

---

## 1. Design principles

1. **Deterministic first, ML later.** The first working system uses OpenCV
   alignment + reference comparison + geometric rules. YOLO / anomaly models are
   optional add-ons behind interfaces, never a hard dependency.
2. **Explainable over confident.** Every `DEFECTIVE` result answers *what / where /
   why* with measured deviations, not just a probability.
3. **Never upgrade uncertainty to GOOD.** Poor image, failed alignment, or
   contradictory evidence produces `REVIEW`, never a silent pass.
4. **No fake predictions.** If a model is not configured, the system says
   `MODEL NOT CONFIGURED` instead of pretending inference happened.
5. **Right tool per task.** OpenCV for geometry/imaging, (optional) YOLO for
   component localization, a dedicated decision engine for the verdict.
6. **Modular.** Swappable image sources, swappable comparison backend, swappable
   detector — all behind small interfaces.

---

## 2. Three layers

```
┌──────────────────────────────────────────────────────────┐
│  OPERATOR DASHBOARD (React)                               │
│  Inspect · History · References · Analytics               │
└───────────────────────────┬──────────────────────────────┘
                            │  REST / JSON  (FastAPI)
┌───────────────────────────┴──────────────────────────────┐
│  GENERIC INSPECTION ENGINE                                │
│  capture → preprocess → detect → align → inspect regions  │
│         → compare vs reference → decide → visualize       │
└───────────────────────────┬──────────────────────────────┘
                            │  InspectionProfile interface
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
   PCB profile          Box profile        (future profiles)
   ref image +          ref image +
   region config        region config
```

The engine does not know what a "PCB" is. It operates on a **profile**: a reference
image plus a list of inspection **regions**, each with expected position and
tolerances. The box product (`BOX_MODEL_001`, `scripts/make_synthetic_box.py`) is
exactly this — a reference image + `regions.json` — and runs the identical
pipeline. `kind` is a display label; no engine code branches on it.

---

## 3. Backend module map

```
backend/app/
  main.py                 FastAPI app, router wiring, static media, startup
  config.py               Settings (env + .env). No hard-coded paths/tolerances.
  logging_config.py       Structured logging setup

  api/
    routes_inspection.py  POST /inspect, /inspect_live, /inspect_multi, GET /inspections/{id}
    routes_reference.py    reference CRUD + activate + autodetect_regions
    routes_history.py      list/filter inspections, CSV export
    routes_camera.py       GET /camera/devices, /camera/preview (MJPEG)
    routes_station.py      GET /station/state, POST /station/trigger

  sources/                Image input abstraction (decoupled from engine)
    base.py               ImageSource
    file_source.py        FileSource  (path on disk)
    upload_source.py      UploadSource (bytes from HTTP)
    camera_source.py      CameraSource / StreamSource (USB webcam or phone IP cam)
    camera_hub.py         one shared background capture per source (preview + snapshot)

  station/                Physical bench station (optional, ESP32 over Wi-Fi)
    controller.py         StationController — last verdict + monotonic counter

  inspection/             The engine (pure functions + small dataclasses)
    preprocessing.py      resize, grayscale, image-quality checks
    detection.py          find + perspective-rectify the board in a real photo
    alignment.py          ORB homography → ECC fallback; board_ssim() check
    reference_checker.py  per-region compare: template match (+ rotation sweep), ECC angle, SSIM
    defect_detector.py    turns region measurements into typed Defect records
    component_match.py    fuse YOLO detections with region results (WRONG_COMPONENT, corroboration)
    multiview.py          N cameras -> N single-view inspections -> one combined verdict
    decision_engine.py    stage gating → GOOD / DEFECTIVE / REVIEW + reasons
    visualization.py      annotated image + montage (original|cropped|aligned|annotated)
    pipeline.py           orchestrates the stages, times them, persists result + media

  profiles/
    base.py               InspectionProfile (regions, reference, tolerances)
    registry.py           load profiles from data/references/*
    pcb.py                PCB-specific defaults / helpers

  models/                 OPTIONAL ML — behind interfaces, disabled by default
    __init__.py           build_component_detector(cfg) — YOLO if configured, else Null
    component_detector.py ComponentDetector interface + NullComponentDetector
    yolo_detector.py      YOLOComponentDetector (lazy Ultralytics import; .pt if present)
    anomaly_detector.py   AnomalyDetector interface (PatchCore/EfficientAD later)

  schemas/                Pydantic models + enums (the API contract)
    inspection.py         InspectionResult, InspectionStatus, ...
    defect.py             Defect, DefectType
    reference.py          Reference, Region, Tolerances

  storage/
    db.py                 SQLite connection + schema
    inspection_repository.py
    reference_repository.py

  demo.py                 CLI: python -m app.demo --image ... | --camera
```

---

## 4. Inspection pipeline (stages)

| Stage | Module | Output on failure |
|-------|--------|-------------------|
| A.1 Decode / presence sanity | preprocessing.is_probably_valid_image | `REVIEW` — `INVALID_IMAGE` |
| A.2 Board detection / crop | detection.detect_board | pass full frame through (not fatal) |
| B. Image quality | preprocessing.quality_check | `REVIEW` — `POOR_IMAGE_QUALITY` |
| C. Alignment to reference | alignment.align_to_reference (ORB → ECC fallback) | `REVIEW` — `ALIGNMENT_FAILED` |
| D. Region presence | reference_checker (template match + rotation sweep) | defect `MISSING_COMPONENT` |
| E. Geometric checks | reference_checker (offset, ECC angle) | defect `SHIFTED` / `ROTATED_COMPONENT` |
| F. Visual anomaly | reference_checker (SSIM / diff) + (later) anomaly model | defect `VISUAL_ANOMALY` |
| F.5 Object detector (optional) | component_match + models/yolo_detector | defect `WRONG_COMPONENT`; corroboration |
| G. Decision | decision_engine (+ registration-trust + detector-contradiction guards) | final status + explanation |

**Stage A.2 — board detection.** Real photos put the board inside a larger,
cluttered frame at an angle. `detect_board` finds the largest board-like
quadrilateral (Canny → dilate/close → `approxPolyDP`), falls back to the largest
Otsu-saturation blob's `minAreaRect`, sanity-checks the quad's aspect ratio
against the reference, then perspective-rectifies to a tight crop. If the board
already fills the frame (tight fixture) or nothing board-like is found, the image
passes through unchanged and `detection.found = false` — alignment is then the
real gate. Disable via `AOI_DETECT_ENABLED=false`.

**Stage C — ECC fallback.** When ORB matching is too weak (few inliers, failed
homography, or a homography with low reprojection error but poor global match),
`align_to_reference` retries with direct intensity-based ECC (`MOTION_AFFINE`,
downscaled) and keeps whichever result has the higher whole-board SSIM.

**Stage G — registration-trust guard.** If alignment reports success but the
aligned board's whole-frame SSIM is below `AOI_DECISION_MIN_BOARD_SSIM` *and*
most regions read as missing, the registration is treated as untrustworthy →
`REVIEW` (`CONTRADICTORY`), never `DEFECTIVE`/`GOOD`. Stops a misregistration from
masquerading as "every component missing".

**Stage F.5 — object detector (optional YOLO).** Runs only when
`AOI_YOLO_MODEL_PATH` points at a real model file (`build_component_detector`);
otherwise the result carries `model_status = "MODEL NOT CONFIGURED"` and the
deterministic verdict stands unchanged — inference is never faked. When active,
`component_match.fuse` binds each detection to a region (IoU / containment) and:

- detected class ≠ the region's `expected_class` → **`WRONG_COMPONENT`** defect
  (critical → `DEFECTIVE`) — something the template pipeline structurally cannot catch;
- detector *agrees* / *disagrees* with the template-match "present" call → recorded
  on the `RegionMeasurement` (`detector_agreement`), surfaced in the UI;
- a deterministic `MISSING`/`SHIFTED`/`ROTATED` call that the detector *contradicts*
  is not decided by the engine → **`REVIEW` (`CONTRADICTORY`)**, unless other
  uncontested critical defects remain.

YOLO **adds** evidence; it never overrides a clean deterministic verdict.
Class names are normalized to each reference's vocabulary via
`AOI_YOLO_CLASS_ALIASES`. Training / eval / dataset-prep are separate scripts
(`scripts/prepare_dataset.py`, `train_yolo.py`, `eval_detector.py`) — never run in
the web server. No detector ships; no mAP is claimed until `eval_detector.py` runs
on a held-out split.

Alignment metadata returned to the caller:

```json
{ "success": true, "rotation_deg": 0.7, "scale": 1.01,
  "translation_px": [3.2, -1.1], "inliers": 214, "alignment_error_px": 0.8 }
```

A per-region **colour check** (`reference_checker._color_delta`) also computes the
CIELAB distance between the region's mean colour in the aligned image vs the
reference — a wrong-colour part that grayscale template matching / SSIM would
pass. It is gated by the whole-board SSIM (`AOI_REGION_ANOMALY_MIN_BOARD_SSIM`):
on a marginally registered board, colour/visual anomalies are suppressed and the
case goes to REVIEW rather than DEFECTIVE.

### Per-region measurement (deterministic, no ML)

1. Crop the reference region patch.
2. `cv2.matchTemplate` of that patch inside a search window in the aligned test
   image → best-match location + peak correlation.
3. Peak correlation `< missing_threshold` → **MISSING_COMPONENT**.
4. Else offset from expected center → if `> position_tolerance_px` → **SHIFTED**
   (report measured deviation in px and, if calibrated, mm).
5. `cv2.findTransformECC` (MOTION_EUCLIDEAN) on the aligned patches → rotation
   angle; `> rotation_tolerance_deg` → **ROTATED_COMPONENT**.
6. SSIM + normalized abs-diff of the aligned patch → `VISUAL_ANOMALY` score.

Confidence per defect is derived from the margin between the measured value and its
tolerance (and from correlation / SSIM). The formula lives in `defect_detector.py`
and is documented there — it is a calibrated heuristic, not a model probability.

---

## 5. Decision engine

```
if not alignment.success            -> REVIEW  (ALIGNMENT_FAILED)
elif quality.failed                  -> REVIEW  (POOR_IMAGE_QUALITY)
elif any critical defect             -> DEFECTIVE
elif visual anomaly above hard band  -> DEFECTIVE
elif any borderline / low confidence -> REVIEW  (LOW_CONFIDENCE / CONTRADICTORY)
else                                 -> GOOD
```

Thresholds and tolerances come from `config.py` (global defaults) and per-region
overrides in the profile. Nothing is hard-coded in the engine.

---

## 6. Data layout

```
data/
  references/<REF_ID>/reference.png      known-good image
  references/<REF_ID>/regions.json       region + tolerance definitions
  test/                                  repeatable test images (synthetic + real)
  samples/                               a few checked-in demo images
  raw/  processed/                       dataset staging (PCB-SAID / DeepPCB / MVTec)
outputs/
  <inspection_id>/original.png aligned.png annotated.png result.json
db/inspection.sqlite
```

External datasets are dropped under `data/` without changing pipeline code. A YOLO
annotation export path is provided by `scripts/prepare_dataset.py` (later milestone).

---

## 7. Multi-camera

`inspection/multiview.py` + `POST /api/inspections/inspect_multi`
(`{views:[{name, source, reference_id?}]}`, 1–4 views). Each view is a full,
independent `run_inspection` (own alignment / regions / defects / media). The
combined `MultiViewResult`: `status` = worst view (DEFECTIVE > REVIEW > GOOD),
`defects` = union prefixed `view/component`, `overall_confidence` = min, plus a
montage of all annotated views. Stored with `result_type="multi"`;
`GET /inspections/{id}` returns `InspectionResult | MultiViewResult`. Dashboard:
Inspect → **Multi-camera** mode.

## 8. Physical station (optional)

`app/station/` + `hardware/`. An ESP32 on the LAN polls `GET /api/station/state`
(~2.5 Hz) and drives a green / red LED stack (REVIEW = both LEDs on) and a servo
reject gate from `verdict` + `reject`. `POST /api/station/trigger` grabs a frame
from `AOI_STATION_SOURCE` — or fans out over `AOI_STATION_VIEWS` for multi-camera
— and inspects it. Every inspection (station, dashboard upload, live camera,
multi-cam) bumps the station `counter`, so the lamp stack always reflects the
latest result. Entirely inert unless `AOI_STATION_ENABLED=true`. Setup:
`hardware/README.md`.

## 9. Extension points (interfaces exist, implementations later)

- `AnomalyDetector` → PatchCore / EfficientAD (interface in `models/`)
- `station` → PLC / real conveyor, multiple reject bins
- Decision engine hooks for human-review feedback / active learning
- `storage` repositories → object storage / Postgres

---

## 10. Milestones (all delivered)

1. **M1:** repo + config + `ImageSource` + preprocessing + alignment + reference
   storage + region compare + decision engine + annotated output + API + operator
   dashboard + history. Real GOOD / DEFECTIVE / REVIEW end-to-end; synthetic PCB
   generator for a hardware-free demo.
2. **M2:** real-camera hardening (phone-as-webcam + upload), board detect/crop,
   ECC alignment fallback, dataset structure + manifest, one-command
   `run_dataset.py` (original / cropped / aligned / annotated / montage / JSON).
3. **Live camera:** `camera_hub`, MJPEG preview, `inspect_live`, dashboard
   Webcam / Stream modes + continuous "live inspection".
4. **M3:** optional YOLO component detector behind `build_component_detector`;
   `WRONG_COMPONENT` + corroboration + contradiction→REVIEW; `prepare_dataset` /
   `train_yolo` / `eval_detector`; dataset placement docs; model-disabled fallback.
5. **M4:** polished operator dashboard; second **box** profile (same engine);
   per-region CIELAB colour check.
6. **Physical station:** ESP32-over-Wi-Fi lamp stack + servo reject gate +
   trigger; `app/station/` + `hardware/`.
