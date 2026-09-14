import { useState } from "react";
import { api } from "../api";
import type { MultiViewResult, Reference } from "../types";

interface Row {
  name: string;
  source: string;
  reference_id: string;
  preview: boolean;
}

interface Props {
  refs: Reference[];
  defaultRefId: string;
  disabled: boolean;
  onResult: (r: MultiViewResult) => void;
  onError: (msg: string) => void;
  onBusyChange: (b: boolean) => void;
}

export function MultiCamCapture({
  refs,
  defaultRefId,
  disabled,
  onResult,
  onError,
  onBusyChange,
}: Props) {
  const [rows, setRows] = useState<Row[]>([
    { name: "cam-1", source: "", reference_id: defaultRefId, preview: false },
    { name: "cam-2", source: "", reference_id: defaultRefId, preview: false },
  ]);
  const [busy, setBusy] = useState(false);

  const set = (i: number, patch: Partial<Row>) =>
    setRows((rs) => rs.map((r, j) => (j === i ? { ...r, ...patch } : r)));

  const run = async () => {
    const views = rows
      .filter((r) => r.source.trim())
      .map((r) => ({ name: r.name.trim() || "cam", source: r.source.trim(), reference_id: r.reference_id }));
    if (views.length < 1) return onError("Add at least one camera source.");
    setBusy(true);
    onBusyChange(true);
    onError("");
    try {
      onResult(await api.inspectMulti(views));
    } catch (e) {
      onError(String((e as Error).message ?? e));
    } finally {
      setBusy(false);
      onBusyChange(false);
    }
  };

  return (
    <div className="stack">
      {rows.map((r, i) => (
        <div className="panel" key={i} style={{ background: "var(--panel-2)" }}>
          <div className="row">
            <label className="field" style={{ width: 110 }}>
              Name
              <input type="text" value={r.name} onChange={(e) => set(i, { name: e.target.value })} />
            </label>
            <label className="field" style={{ flex: 1, minWidth: 220 }}>
              Source (URL or index)
              <input
                type="text"
                value={r.source}
                placeholder="http://192.168.1.42:8080/video   or   0"
                onChange={(e) => set(i, { source: e.target.value })}
              />
            </label>
            <label className="field" style={{ minWidth: 180 }}>
              Reference
              <select
                value={r.reference_id}
                onChange={(e) => set(i, { reference_id: e.target.value })}
              >
                {refs.map((ref) => (
                  <option key={ref.id} value={ref.id}>
                    {ref.kind} · {ref.id}
                  </option>
                ))}
              </select>
            </label>
            <button
              className="btn ghost"
              style={{ alignSelf: "end" }}
              onClick={() => set(i, { preview: !r.preview })}
              disabled={!r.source.trim()}
            >
              {r.preview ? "Hide" : "Preview"}
            </button>
            {rows.length > 1 && (
              <button
                className="btn ghost"
                style={{ alignSelf: "end" }}
                onClick={() => setRows((rs) => rs.filter((_, j) => j !== i))}
              >
                ✕
              </button>
            )}
          </div>
          {r.preview && r.source.trim() && (
            <div className="image-frame" style={{ marginTop: 10, maxWidth: 420 }}>
              <img src={api.cameraPreviewUrl(r.source.trim())} alt={r.name} />
            </div>
          )}
        </div>
      ))}

      <div className="row">
        {rows.length < 4 && (
          <button
            className="btn secondary"
            onClick={() =>
              setRows((rs) => [
                ...rs,
                { name: `cam-${rs.length + 1}`, source: "", reference_id: defaultRefId, preview: false },
              ])
            }
          >
            + Add camera
          </button>
        )}
        <button className="btn" onClick={run} disabled={disabled || busy}>
          {busy ? <span className="spinner" /> : "Run multi-view inspection"}
        </button>
      </div>
      <p className="muted" style={{ fontSize: 12, margin: 0 }}>
        Each camera is inspected against its own reference; the verdict is the worst
        view. Point 2–3 phones / webcams at the object (e.g. front · top · back).
      </p>
    </div>
  );
}
