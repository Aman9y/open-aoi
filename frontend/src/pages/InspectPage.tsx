import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { AnyResult, Reference } from "../types";
import { isMulti } from "../types";
import { ResultView } from "../components/ResultView";
import { MultiViewResultView } from "../components/MultiViewResultView";
import { CameraCapture } from "../components/CameraCapture";
import { MultiCamCapture } from "../components/MultiCamCapture";
import { StationCard } from "../components/StationCard";

type Mode = "upload" | "webcam" | "stream" | "multi";
const MODES: { id: Mode; label: string }[] = [
  { id: "upload", label: "Upload image" },
  { id: "webcam", label: "Webcam" },
  { id: "stream", label: "Stream URL" },
  { id: "multi", label: "Multi-camera" },
];

export function InspectPage() {
  const [refs, setRefs] = useState<Reference[]>([]);
  const [refId, setRefId] = useState<string>("");
  const [mode, setMode] = useState<Mode>("upload");

  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string>("");
  const [result, setResult] = useState<AnyResult | null>(null);
  const [drag, setDrag] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api
      .listReferences()
      .then((rs) => {
        setRefs(rs);
        const active = rs.find((r) => r.active) ?? rs[0];
        if (active) setRefId(active.id);
      })
      .catch((e) => setErr(String(e.message ?? e)));
  }, []);

  const pick = useCallback((f: File | null) => {
    setFile(f);
    setResult(null);
    setErr("");
    setPreview(f ? URL.createObjectURL(f) : "");
  }, []);

  const runUpload = async () => {
    if (!file) return;
    setBusy(true);
    setErr("");
    setResult(null);
    try {
      setResult(await api.inspect(file, refId || undefined));
    } catch (e) {
      setErr(String((e as Error).message ?? e));
    } finally {
      setBusy(false);
    }
  };

  const switchMode = (m: Mode) => {
    setMode(m);
    setResult(null);
    setErr("");
  };

  const activeRef = refs.find((r) => r.id === refId);

  return (
    <>
      <div className="between" style={{ marginBottom: 20 }}>
        <div>
          <h1 className="page-title">Inspection Station</h1>
          <p className="page-sub" style={{ margin: 0 }}>
            Select a product, provide an image or live frame, run a single inspection.
          </p>
        </div>
        {result && (
          <button
            className="btn ghost"
            onClick={() => {
              setResult(null);
              setErr("");
              pick(null);
            }}
          >
            ↺ Inspect another
          </button>
        )}
      </div>

      <StationCard onResult={setResult} />

      <div className="panel stack" style={{ marginBottom: 18 }}>
        <div className="row">
          <label className="field" style={{ minWidth: 300 }}>
            Reference product
            <select value={refId} onChange={(e) => setRefId(e.target.value)}>
              {refs.length === 0 && <option value="">no references — add one first</option>}
              {refs.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.kind} · {r.name} ({r.id}){r.active ? "  — active" : ""}
                </option>
              ))}
            </select>
          </label>
          {activeRef && (
            <span className={"pill " + activeRef.kind} style={{ alignSelf: "flex-end", marginBottom: 3 }}>
              {activeRef.regions.length} inspection regions
            </span>
          )}
        </div>

        <div className="image-tabs">
          {MODES.map((m) => (
            <button
              key={m.id}
              className={mode === m.id ? "active" : ""}
              onClick={() => switchMode(m.id)}
              disabled={busy}
            >
              {m.label}
            </button>
          ))}
        </div>

        {mode === "upload" && (
          <>
            <div className="row">
              <button className="btn" disabled={!file || busy || !refId} onClick={runUpload}>
                {busy ? <span className="spinner" /> : "Run inspection"}
              </button>
              {file && (
                <button className="btn secondary" onClick={() => pick(null)} disabled={busy}>
                  Clear
                </button>
              )}
            </div>

            <div
              className={"dropzone" + (drag ? " drag" : "")}
              onClick={() => inputRef.current?.click()}
              onDragOver={(e) => {
                e.preventDefault();
                setDrag(true);
              }}
              onDragLeave={() => setDrag(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDrag(false);
                pick(e.dataTransfer.files[0] ?? null);
              }}
            >
              {file ? (
                <strong>{file.name}</strong>
              ) : (
                <>
                  Drop a PCB image here, or click to browse.
                  <br />
                  <span className="muted">
                    A phone photo works — the pipeline detects and rectifies the board.
                  </span>
                </>
              )}
              <input
                ref={inputRef}
                type="file"
                accept="image/*"
                hidden
                onChange={(e) => pick(e.target.files?.[0] ?? null)}
              />
            </div>

            {preview && !result && (
              <div className="image-frame" style={{ maxWidth: 420 }}>
                <img src={preview} alt="preview" />
              </div>
            )}
          </>
        )}

        {(mode === "webcam" || mode === "stream") && (
          <CameraCapture
            mode={mode}
            referenceId={refId}
            disabled={!refId}
            onResult={setResult}
            onError={setErr}
            onBusyChange={setBusy}
          />
        )}

        {mode === "multi" && (
          <MultiCamCapture
            refs={refs}
            defaultRefId={refId}
            disabled={refs.length === 0}
            onResult={setResult}
            onError={setErr}
            onBusyChange={setBusy}
          />
        )}

        {err && <div className="notice err">{err}</div>}
      </div>

      {result && (
        <div className="panel">
          {isMulti(result) ? (
            <MultiViewResultView result={result} />
          ) : (
            <ResultView result={result} />
          )}
        </div>
      )}
    </>
  );
}
