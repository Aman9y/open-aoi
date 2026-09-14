import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { InspectionResult } from "../types";
import { LiveStatus } from "./LiveStatus";

type Mode = "webcam" | "stream";
const LIVE_INTERVAL_MS = 1800;

interface Props {
  mode: Mode;
  referenceId: string;
  disabled: boolean;
  onResult: (r: InspectionResult) => void;
  onError: (msg: string) => void;
  onBusyChange: (busy: boolean) => void;
}

export function CameraCapture({
  mode,
  referenceId,
  disabled,
  onResult,
  onError,
  onBusyChange,
}: Props) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]);
  const [deviceId, setDeviceId] = useState<string>("");
  const [webcamOn, setWebcamOn] = useState(false);

  const [urlInput, setUrlInput] = useState("");
  const [connectedSource, setConnectedSource] = useState<string>("");
  const [backendCams, setBackendCams] = useState<{ source: string; label: string }[]>([]);

  const [busy, setBusy] = useState(false);
  const [live, setLive] = useState(false);
  const [liveResult, setLiveResult] = useState<InspectionResult | null>(null);
  const [liveAt, setLiveAt] = useState(0);
  const liveRef = useRef(false);

  const ready = mode === "webcam" ? webcamOn : !!connectedSource;

  const setBusyBoth = useCallback(
    (b: boolean) => {
      setBusy(b);
      onBusyChange(b);
    },
    [onBusyChange],
  );

  // ---- webcam lifecycle -------------------------------------------------
  const stopWebcam = useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    setWebcamOn(false);
  }, []);

  const startWebcam = useCallback(
    async (id?: string) => {
      stopWebcam();
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: id ? { deviceId: { exact: id } } : { facingMode: "environment" },
          audio: false,
        });
        streamRef.current = stream;
        if (videoRef.current) videoRef.current.srcObject = stream;
        setWebcamOn(true);
        const list = (await navigator.mediaDevices.enumerateDevices()).filter(
          (d) => d.kind === "videoinput",
        );
        setDevices(list);
        if (!id && list[0]) setDeviceId(list[0].deviceId);
      } catch (e) {
        onError(
          "Could not access a webcam: " +
            (e as Error).message +
            ". Grant camera permission, or use Stream URL mode for a phone IP camera.",
        );
      }
    },
    [onError, stopWebcam],
  );

  useEffect(() => {
    setLive(false);
    setLiveResult(null);
    if (mode === "webcam") startWebcam(deviceId || undefined);
    else stopWebcam();
    return stopWebcam;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode]);

  useEffect(() => {
    if (mode === "stream")
      api.cameraDevices().then(setBackendCams).catch(() => setBackendCams([]));
  }, [mode]);

  // ---- single-frame capture -----------------------------------------
  const grabWebcamFile = async (): Promise<File | null> => {
    const video = videoRef.current;
    if (!video || !video.videoWidth) return null;
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d")!.drawImage(video, 0, 0);
    const blob: Blob | null = await new Promise((res) =>
      canvas.toBlob((b) => res(b), "image/jpeg", 0.95),
    );
    return blob ? new File([blob], "webcam.jpg", { type: "image/jpeg" }) : null;
  };

  const inspectOnce = useCallback(
    async (save: boolean): Promise<InspectionResult | null> => {
      if (mode === "webcam") {
        const file = await grabWebcamFile();
        if (!file) throw new Error("Webcam not ready yet.");
        return api.inspect(file, referenceId, save);
      }
      return api.inspectLive(connectedSource, referenceId, save);
    },
    [mode, referenceId, connectedSource],
  );

  const captureAndRecord = async () => {
    setBusyBoth(true);
    onError("");
    try {
      const r = await inspectOnce(true);
      if (r) onResult(r);
    } catch (e) {
      onError(String((e as Error).message ?? e));
    } finally {
      setBusyBoth(false);
    }
  };

  // ---- live loop ----------------------------------------------------
  useEffect(() => {
    liveRef.current = live;
    if (!live) return;
    let cancelled = false;
    (async () => {
      while (!cancelled && liveRef.current) {
        try {
          const r = await inspectOnce(false);
          if (!cancelled && r) {
            setLiveResult(r);
            setLiveAt(Date.now());
          }
        } catch (e) {
          if (!cancelled) {
            onError(String((e as Error).message ?? e));
            setLive(false);
            break;
          }
        }
        await new Promise((res) => setTimeout(res, LIVE_INTERVAL_MS));
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [live, inspectOnce]);

  // ---- render --------------------------------------------------------
  const previewEl =
    mode === "webcam" ? (
      <video ref={videoRef} autoPlay muted playsInline style={{ width: "100%" }} />
    ) : connectedSource ? (
      <img
        src={api.cameraPreviewUrl(connectedSource)}
        alt="camera preview"
        onError={() =>
          onError(
            `Could not open stream '${connectedSource}'. Check the URL (most phone apps ` +
              `need a trailing /video) and that both devices are on the same network.`,
          )
        }
      />
    ) : (
      <span className="muted">connect a stream to preview</span>
    );

  return (
    <div className="stack">
      {mode === "webcam" && devices.length > 1 && (
        <label className="field">
          Camera
          <select
            value={deviceId}
            onChange={(e) => {
              setDeviceId(e.target.value);
              startWebcam(e.target.value);
            }}
          >
            {devices.map((d, i) => (
              <option key={d.deviceId} value={d.deviceId}>
                {d.label || `Camera ${i + 1}`}
              </option>
            ))}
          </select>
        </label>
      )}

      {mode === "stream" && (
        <>
          <div className="row">
            <label className="field" style={{ flex: 1, minWidth: 260 }}>
              Stream URL or device index
              <input
                type="text"
                value={urlInput}
                placeholder="http://192.168.1.42:8080/video   or   0"
                onChange={(e) => setUrlInput(e.target.value)}
              />
            </label>
            <button
              className="btn secondary"
              disabled={!urlInput}
              onClick={() => setConnectedSource(urlInput.trim())}
              style={{ alignSelf: "end" }}
            >
              Connect
            </button>
          </div>
          {backendCams.length > 0 && (
            <div className="row">
              <span className="muted" style={{ fontSize: 12 }}>local:</span>
              {backendCams.map((c) => (
                <button
                  key={c.source}
                  className="btn secondary"
                  onClick={() => {
                    setUrlInput(c.source);
                    setConnectedSource(c.source);
                  }}
                >
                  {c.label}
                </button>
              ))}
            </div>
          )}
        </>
      )}

      <div className="row">
        <button
          className={"btn" + (live ? " danger" : "")}
          disabled={disabled || !ready || !referenceId}
          onClick={() => setLive((v) => !v)}
        >
          {live ? "Stop live inspection" : "Start live inspection"}
        </button>
        <button
          className="btn secondary"
          disabled={disabled || busy || !ready || !referenceId}
          onClick={captureAndRecord}
        >
          {busy ? <span className="spinner" /> : live ? "Record this frame" : "Capture & inspect"}
        </button>
      </div>

      <div className="row" style={{ alignItems: "flex-start", gap: 16 }}>
        <div className="image-frame" style={{ flex: 1, maxWidth: 520 }}>
          {previewEl}
        </div>
        {live && <LiveStatus result={liveResult} updatedAt={liveAt} running={live} />}
      </div>

      <p className="muted" style={{ fontSize: 12, margin: 0 }}>
        {mode === "webcam"
          ? "Any camera the browser can see (USB webcam, or a phone via iVCam / EpocCam / Phone Link). Frames are captured in the browser."
          : "Phone on the same Wi-Fi: run an IP-webcam app and paste its stream URL (e.g. http://<phone-ip>:8080/video). Live mode runs an inspection every ~2 s without saving; use Record to keep one."}
      </p>
    </div>
  );
}
