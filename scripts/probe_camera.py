"""Check a camera / phone connection before running an inspection.

    py scripts/probe_camera.py --stream http://192.168.1.42:8080/video
    py scripts/probe_camera.py --camera 0
    py scripts/probe_camera.py --list          # enumerate local capture devices

Grabs a few frames, reports resolution / FPS / latency, and saves a preview to
outputs/probe/<source>.jpg so you can confirm framing and focus.
"""

from __future__ import annotations

import argparse
import os
import sys
import time

os.environ.setdefault("OPENCV_LOG_LEVEL", "FATAL")  # hush backend-probe chatter

import _bootstrap  # noqa: F401,E402
import cv2  # noqa: E402

try:
    cv2.setLogLevel(0)
except Exception:  # noqa: BLE001
    pass

from app.config import get_settings  # noqa: E402

# On Windows the default MSMF backend noisily probes for Orbbec depth cameras;
# DirectShow is quieter and enumerates ordinary webcams / virtual cams fine.
_LOCAL_BACKEND = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY


def _open_local(index: int) -> cv2.VideoCapture:
    cap = cv2.VideoCapture(index, _LOCAL_BACKEND)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    return cap


def _list_devices(max_index: int = 6) -> None:
    print(f"scanning local capture devices (0..{max_index})…")
    found = 0
    for i in range(max_index + 1):
        cap = _open_local(i)
        if cap.isOpened():
            ok, frame = cap.read()
            if ok and frame is not None:
                h, w = frame.shape[:2]
                print(f"  [{i}] OK  {w}x{h}")
                found += 1
        cap.release()
    print(f"done — {found} device(s). Use: py scripts/probe_camera.py --camera <index>")


def _probe(cap: cv2.VideoCapture, label: str, frames: int = 30) -> None:
    if not cap.isOpened():
        raise SystemExit(f"could not open {label}")

    # warm up
    for _ in range(5):
        cap.read()

    t0 = time.perf_counter()
    ok_count = 0
    last = None
    for _ in range(frames):
        ok, frame = cap.read()
        if ok and frame is not None:
            ok_count += 1
            last = frame
    dt = time.perf_counter() - t0

    if last is None:
        raise SystemExit(f"{label} opened but returned no frames")

    h, w = last.shape[:2]
    fps = ok_count / dt if dt else 0.0
    reported_fps = cap.get(cv2.CAP_PROP_FPS)
    print(f"\n{label}")
    print(f"  resolution     : {w} x {h}")
    print(f"  measured FPS   : {fps:.1f}  (driver reports {reported_fps:.0f})")
    print(f"  frames ok      : {ok_count}/{frames}")
    print(f"  ~latency/frame : {1000 * dt / max(1, ok_count):.0f} ms")

    blur = cv2.Laplacian(cv2.cvtColor(last, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var()
    print(f"  sharpness      : {blur:.0f} (variance of Laplacian; higher = sharper)")

    out = get_settings().outputs_dir / "probe"
    out.mkdir(parents=True, exist_ok=True)
    name = label.replace("/", "_").replace(":", "_").replace(" ", "_")[:60]
    path = out / f"{name}.jpg"
    cv2.imwrite(str(path), last)
    print(f"  preview saved  : {path}")
    print("\nlooks good? run an inspection:")
    print("  py -m app.demo --stream <url>       (from backend/, or add --reference <id>)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--stream", help="phone / IP camera stream URL")
    g.add_argument("--camera", type=int, metavar="INDEX", help="local capture device index")
    g.add_argument("--list", action="store_true", help="enumerate local capture devices")
    args = ap.parse_args()

    if args.list:
        _list_devices()
        return
    if args.stream:
        _probe(cv2.VideoCapture(args.stream), f"stream {args.stream}")
    else:
        _probe(_open_local(args.camera), f"camera {args.camera}")


if __name__ == "__main__":
    main()
