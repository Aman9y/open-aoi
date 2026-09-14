@echo off
setlocal
cd /d "%~dp0"

if not exist data\references\PCB_MODEL_001 (
  echo Generating demo references + datasets...
  .venv\Scripts\python.exe scripts\make_synthetic_pcb.py
  .venv\Scripts\python.exe scripts\make_synthetic_box.py
)

REM ================= ESP32 STATION =================
REM Remove "REM " from the next two lines to drive the LEDs / servo.
REM   AOI_STATION_SOURCE=0  is the laptop webcam  (or a phone stream URL)
set AOI_STATION_ENABLED=true
set AOI_STATION_SOURCE=0
set AOI_SURFACE_REVIEW_SSIM=0.60
set AOI_SURFACE_DEFECT_SSIM=0.55
REM (optional) set AOI_YOLO_MODEL_PATH=models\component_detector.pt
REM ================================================

echo.
echo   API           http://localhost:8000     (docs at /docs)
echo   ESP32 sketch  put this PC's IPv4 (run: ipconfig) in BACKEND_HOST
if defined AOI_STATION_ENABLED (
  echo   Station       ENABLED   camera=%AOI_STATION_SOURCE%
) else (
  echo   Station       disabled  ^(LEDs / servo will not react^)
)
echo.

.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --app-dir backend
