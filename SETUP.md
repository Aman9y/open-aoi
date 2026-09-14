# SETUP

Prototype — Windows / macOS / Linux. Python 3.11+ and Node 18+.

## 1. Backend

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r backend/requirements.txt
```

Generate the demo reference + a labelled dataset of simulated phone-camera photos
(no hardware needed):

```bash
python scripts/make_synthetic_pcb.py
```

Run one inspection from the CLI:

```bash
cd backend
python -m app.demo --image ../data/datasets/synthetic_v1/images/defect_multi.png
```

Run the whole dataset (per-image montage + JSON, summary table, contact sheet):

```bash
python scripts/run_dataset.py --dataset synthetic_v1
python scripts/evaluate.py --dataset synthetic_v1
```

Start the API:

```bash
cd backend
python -m uvicorn app.main:app --reload --port 8000
```

- API docs: http://localhost:8000/docs
- Health: http://localhost:8000/api/health

## 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 (dev server proxies `/api` and `/media` to `:8000`).

## 3. Tests

```bash
pip install -r backend/requirements.txt   # includes pytest, httpx
python -m pytest tests/ -q
```

## 3b. Optional — YOLO component detector

Not required for the demo. To enable class-level checks (`WRONG_COMPONENT`,
present/missing corroboration, region auto-detect):

```bash
pip install -r backend/requirements-ml.txt          # ~1-2 GB (PyTorch)
python scripts/prepare_dataset.py --format voc --src data/raw/pcb_said --name pcb_said_yolo
python scripts/train_yolo.py --data data/datasets/pcb_said_yolo/data.yaml
python scripts/eval_detector.py --data data/datasets/pcb_said_yolo/data.yaml \
                                --weights models/component_detector.pt
```
Then set `AOI_YOLO_MODEL_PATH=models/component_detector.pt`. Dataset placement:
[data/raw/README.md](data/raw/README.md).

## 4. Configuration

All tunables live in `backend/app/config.py` and can be overridden with env vars
(prefix `AOI_`) or a `.env` file in the repo root. See `.env.example`.

Key values to calibrate for a real camera + lighting rig:

| Setting | Meaning |
|---|---|
| `AOI_QUALITY_BLUR_MIN` | min sharpness (variance of Laplacian) |
| `AOI_QUALITY_CONTRAST_MIN` | min grey-level std dev |
| `AOI_ALIGN_MAX_ERROR_PX` | max acceptable alignment reprojection error |
| `AOI_REGION_POSITION_TOL_PX` | default per-component position tolerance |
| `AOI_REGION_ROTATION_TOL_DEG` | default per-component rotation tolerance |
| `AOI_MM_PER_PX` | pixel→mm scale for deviation reporting (0 = disabled) |

## 5. Camera / phone

The upload path needs no hardware. Live capture works from the **dashboard Inspect
page** (Webcam / Stream URL modes) and from the CLI.

### Phone over Wi-Fi (recommended)

Both devices on the same network.

- **Android:** install *IP Webcam*, tap **Start server** → it shows e.g.
  `http://192.168.1.42:8080`. The stream URL is that **+ `/video`**.
- **iPhone:** install *DroidCam* (stream `http://<phone-ip>:4747/video`) or use
  *iVCam* / *EpocCam*, which register the phone as a Windows webcam instead.

Test it, then inspect:

```bash
python scripts/probe_camera.py --stream http://192.168.1.42:8080/video
```

Dashboard: **Inspect → Stream URL**, paste the URL, **Connect**, **Capture & inspect**.
CLI: `python -m app.demo --stream http://192.168.1.42:8080/video`

### Phone over USB (more stable — no Wi-Fi jitter)

*DroidCam* has a USB mode; enable USB debugging (Android) / plug in (iPhone), pick
USB in the DroidCam PC client. It exposes a stream URL or webcam device — use it
with Stream URL mode or `--camera <index>`.

### Phone or camera as a webcam

Windows *Phone Link*, *iVCam*, *EpocCam*, or a plain USB webcam show up as a camera
device. Dashboard: **Inspect → Webcam** (browser picks it up, grant permission).
CLI: `python scripts/probe_camera.py --list` then `python -m app.demo --camera <n>`.

### Rig tips

Mount the phone on a gooseneck/tripod pointing straight down at a taped board
outline; even 45° lighting, no overhead glare. USB tether for the live demo, keep
upload as the fallback if venue Wi-Fi is unreliable.
