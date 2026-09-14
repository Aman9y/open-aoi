# Implementation checklist

## Milestone 1 — deterministic vertical slice + dashboard  ✅ (this milestone)

- [x] Repo scaffold, venv, `.gitignore`, `pyproject.toml`
- [x] `ARCHITECTURE.md`, `README.md`, `SETUP.md`
- [x] Config via `config.py` + env (`AOI_*`) — no hard-coded paths/tolerances
- [x] Logging setup
- [x] `ImageSource` abstraction: `FileSource`, `UploadSource`, `CameraSource`, `StreamSource`
- [x] Preprocessing: resize, grayscale, image-quality gate (blur/exposure/contrast)
- [x] Alignment: ORB + RANSAC homography, metadata (rotation/scale/translation/error), fail → REVIEW
- [x] Reference store (filesystem): create / list / activate / delete / regions
- [x] Per-region comparison: template match (+ rotation sweep), ECC angle, SSIM
- [x] Typed defects: MISSING / SHIFTED / ROTATED / VISUAL_ANOMALY with what/where/why
- [x] Decision engine: GOOD / DEFECTIVE / REVIEW truth table; uncertainty never → GOOD
- [x] Annotated image (region boxes, defect labels, diff heatmap) + aligned + original
- [x] Result schema with enums; `result.json` per inspection
- [x] API: `/inspections/inspect`, `/inspections/{id}`, references CRUD, history, stats, CSV
- [x] SQLite history repository
- [x] Static media serving
- [x] Operator dashboard (React): Inspect / History / Analytics / References
- [x] CLI demo: `python -m app.demo --image | --camera | --stream`
- [x] Synthetic PCB generator (hardware-free demo) — real inspection, not fake output
- [x] Evaluation script with FALSE ACCEPTS reporting
- [x] Tests: alignment, component inspection, decision engine, API (22 passing)
- [x] `models/` interfaces present (`ComponentDetector`, `AnomalyDetector`) — null impls

## Milestone 2 — real camera images  ✅

- [x] PCB detect / crop before alignment — largest board-like quad (Canny + approxPolyDP)
      with an Otsu-saturation fallback and aspect-ratio sanity vs the reference
      (`inspection/detection.py`); passes through when the board already fills the frame
- [x] Robustness pass on simulated phone photos — cluttered desk, off-axis placement,
      perspective, glare, shadow, sensor noise (`scripts/make_synthetic_pcb.py` `photograph()`)
- [x] ECC intensity-alignment fallback when ORB is weak; pick the higher board-SSIM result
- [x] Registration-trust guard — "alignment ok" but low board SSIM + most regions missing
      ⇒ REVIEW, never DEFECTIVE/GOOD
- [x] Structured dataset: `data/datasets/<name>/{manifest.json, images/}`
- [x] One command — `scripts/run_dataset.py`: per-image original/cropped/aligned/annotated/
      montage + result.json, plus `summary.{md,csv}` and `contact_sheet.png`
- [x] `scripts/evaluate.py` — manifest-aware; accuracy/precision/recall/F1/FP/FN/localization
      + FALSE ACCEPTS
- [x] Tests: detection (cluttered / passthrough / end-to-end) — 26 passing total
- [ ] Calibrate quality + tolerance thresholds on the **physical** rig (needs real photos)
- [ ] White-balance / exposure normalization for real sensors (deferred — synthetic is controlled)

## Milestone 3 — ML  ✅

- [x] `scripts/prepare_dataset.py` — VOC / COCO / DeepPCB / YOLO → YOLO format + data.yaml
- [x] `scripts/train_yolo.py` (Ultralytics wrapper, runs outside the server)
- [x] `scripts/eval_detector.py` — held-out mAP/P/R, the only accuracy source
- [x] `data/raw/README.md` — exact PCB-SAID / DeepPCB / MVTec placement + conversion
- [x] `backend/requirements-ml.txt` — optional; core install stays torch-free
- [x] `models/__init__.py: build_component_detector(cfg)` — cached YOLO or Null
- [x] `YOLOComponentDetector` — lazy Ultralytics import, class-alias normalization
- [x] Stage F.5 `inspection/component_match.py` — bind detections to regions:
      - class mismatch → `WRONG_COMPONENT` (critical)
      - agree / conflict corroboration on `RegionMeasurement`
      - deterministic MISSING/SHIFTED/ROTATED contradicted by detector → REVIEW
- [x] Detection boxes in the annotated image; `model_status` GOOD/`YOLO_ACTIVE`/`MODEL NOT CONFIGURED`
- [x] `POST /api/references/{id}/autodetect_regions` — propose regions from YOLO
- [x] Model-disabled + missing-model-file fallbacks verified (no fake inference)
- [x] Tests: `test_yolo_integration.py` (5) with a scripted fake detector — 33 passing total
- [ ] Actually train on PCB-SAID and record real mAP (needs the dataset + GPU time)

## Live camera in dashboard — continuous mode  ✅

- [x] `POST /inspect` + `/inspect_live` gain `save` flag (live polling → `save=false`)
- [x] Inspect page: **Start live inspection** — re-inspects the feed every ~1.8 s,
      rolling GOOD/DEFECTIVE/REVIEW (`components/LiveStatus.tsx`), not saved
- [x] **Record this frame** saves the current result; **Capture & inspect** = single saved run
- [x] Verified: live polling leaves history untouched; Record adds one row

## Live camera in dashboard  ✅ (pulled forward from M4)

- [x] `sources/camera_hub.py` — one background capture per source (device index or
      stream URL), shared by preview + snapshot, auto-released when idle
- [x] `GET /api/camera/devices` — enumerate local capture indices
- [x] `GET /api/camera/preview?source=…` — MJPEG proxy for an `<img>` tag
- [x] `POST /api/inspections/inspect_live` — `{source, reference_id}` → grab one
      frame → run pipeline (shares plumbing with `/inspect`)
- [x] Inspect page: Upload / Webcam / Stream URL toggle
      - Webcam: `getUserMedia` live preview → capture frame in-browser → `/inspect`
      - Stream URL: MJPEG preview + detected `Camera N` buttons → `/inspect_live`
- [x] `scripts/probe_camera.py` — `--list` / `--stream` / `--camera` connection test
- [x] Tests: `/api/camera/devices`, `/inspect_live` bad-source → 502 (no fake result)

## Milestone 4 — polished demo + second profile  ✅

- [x] **Box profile** — `BOX_MODEL_001` (kind=BOX), `scripts/make_synthetic_box.py`,
      `data/datasets/box_v1/` (11 scenes: missing cap/label/barcode, shifted &
      crooked label, torn seal, wrong cap colour, blur, off-fixture). Same engine,
      zero PCB-specific code. eval: 11/11, localization 1.0, 0 false accepts.
- [x] Shared scene synthesis extracted to `scripts/_scene.py`; `run_dataset.py` /
      `evaluate.py` read `reference_id` from the manifest.
- [x] **Colour check** — `reference_checker` computes per-region CIELAB ΔE vs
      reference; `defect_detector` flags a wrong-colour part (grayscale template
      match / SSIM miss it). Gated by board SSIM so a marginal registration → REVIEW.
- [x] Detection: min-area-rect fallback for low-contrast object edges (the carton).
- [x] Dashboard visual pass — top status bar, sidebar nav, operator "Inspection
      Station" screen with a full-width verdict banner, image tabs
      (annotated/original/cropped/aligned), metrics + explainable defect cards,
      "Inspect another", profile-kind pills, polished History/Analytics/References.
- [x] Tests: `test_box_profile.py` (4) — 37 passing total.
- [ ] Demo script / walkthrough (README covers the flow)

## Physical station — ESP32 over Wi-Fi  ✅

- [x] `app/station/controller.py` — `StationController`: last verdict + monotonic
      `counter`, `reject` flag from `AOI_STATION_REJECT_STATUSES`, ESP32 online tracking
- [x] `GET /api/station/state` (ESP32 poll + dashboard) · `POST /api/station/trigger`
      (button/sensor → capture from `AOI_STATION_SOURCE` → inspect → save)
- [x] Every inspection (station / upload / live) bumps `counter` → lamp stack always current
- [x] `hardware/inspection_station/inspection_station.ino` — WiFi, poll loop,
      debounced button, R/G/Y LED, servo reject gate, buzzer; `hardware/README.md` wiring
- [x] Dashboard `StationCard` on Inspect — connection status + Trigger button +
      last verdict; hidden unless station enabled
- [x] All inert unless `AOI_STATION_ENABLED=true`
- [x] ESP32 sketch matched to the operator's wiring (GREEN=25, RED=26, SERVO=27,
      external 5 V; no amber/buzzer/button) — output-only, REVIEW = both LEDs on

## Multi-camera  ✅

- [x] `inspection/multiview.py` — N views → N independent `run_inspection` → combine
      (worst-of status, union defects prefixed `view/component`, min confidence, montage)
- [x] `POST /api/inspections/inspect_multi` (1–4 views); `MultiViewResult` schema with
      `result_type` discriminator; history + `GET /inspections/{id}` handle both types
- [x] `AOI_STATION_VIEWS` — station trigger fans out over multiple cameras
- [x] Dashboard: **Multi-camera** mode (per-camera name / source / reference + preview),
      `MultiViewResultView` (combined banner + montage + per-view accordion)
- [x] `scripts/check_model.py` — verify a downloaded YOLO `.pt`, print classes,
      suggest `AOI_YOLO_CLASS_ALIASES`, run a test inference
- [x] Tests: multi-view combine + storage — 42 passing total
