import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { AnyResult, StationState } from "../types";

interface LogRow {
  counter: number;
  verdict: string;
  reason: string;
  reject: boolean;
  at: string;
}

export function StationCard({ onResult }: { onResult: (r: AnyResult) => void }) {
  const [st, setSt] = useState<StationState | null>(null);
  const [log, setLog] = useState<LogRow[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [pollBeat, setPollBeat] = useState(0); // shows the dashboard is talking to the backend
  const lastCounter = useRef(-1);

  useEffect(() => {
    let alive = true;
    const poll = () =>
      api
        .stationState()
        .then((s) => {
          if (!alive) return;
          setSt(s);
          setPollBeat((n) => n + 1);
          if (s.counter !== lastCounter.current && lastCounter.current >= 0) {
            setLog((rows) =>
              [
                {
                  counter: s.counter,
                  verdict: s.verdict,
                  reason: s.reason,
                  reject: s.reject,
                  at: new Date().toLocaleTimeString(),
                },
                ...rows,
              ].slice(0, 6),
            );
            if (s.inspection_id) api.getInspection(s.inspection_id).then(onResult).catch(() => {});
          }
          lastCounter.current = s.counter;
        })
        .catch(() => alive && setPollBeat((n) => n + 1));
    poll();
    const t = setInterval(poll, 1500);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, [onResult]);

  if (!st) return null;

  // --- station not enabled: show the fix, don't hide ---
  if (!st.enabled) {
    return (
      <div className="panel" style={{ marginBottom: 18 }}>
        <div className="row" style={{ gap: 10 }}>
          <span className="dot off" />
          <strong>Station</strong>
          <span className="muted" style={{ fontSize: 12 }}>
            not enabled — LEDs / servo won't react
          </span>
        </div>
        <p className="muted" style={{ fontSize: 12, margin: "10px 0 0" }}>
          In <code>start_backend.bat</code> uncomment{" "}
          <code>set AOI_STATION_ENABLED=true</code> and{" "}
          <code>set AOI_STATION_SOURCE=0</code>, then restart it. The ESP32 also
          needs your laptop IP in <code>BACKEND_HOST</code>.
        </p>
      </div>
    );
  }

  const trigger = async () => {
    setBusy(true);
    setErr("");
    try {
      onResult(await api.stationTrigger());
    } catch (e) {
      setErr(String((e as Error).message ?? e));
    } finally {
      setBusy(false);
    }
  };

  const espLabel = st.esp32_online
    ? `ESP32 connected${st.esp32_last_seen_s_ago != null ? ` · polled ${st.esp32_last_seen_s_ago}s ago` : ""}`
    : "ESP32 not seen — flash it with your laptop IP, same Wi-Fi";

  return (
    <div className="panel" style={{ marginBottom: 18 }}>
      <div className="between">
        <div className="row" style={{ gap: 10 }}>
          <span className={"dot" + (st.esp32_online ? "" : " off")} />
          <strong>Station</strong>
          <span className="muted" style={{ fontSize: 12 }}>
            {espLabel} · camera {st.source || "—"}
          </span>
        </div>
        <button className="btn" onClick={trigger} disabled={busy}>
          {busy ? <span className="spinner" /> : "Trigger inspection"}
        </button>
      </div>

      <div className="row" style={{ marginTop: 12, gap: 10 }}>
        <span
          className={"badge " + (st.verdict === "IDLE" ? "REVIEW" : st.verdict)}
          title="latest verdict the ESP32 is showing"
        >
          {st.verdict}
        </span>
        <span className="muted" style={{ fontSize: 12 }}>
          {st.counter === 0
            ? "no inspection yet — LEDs off is correct"
            : `#${st.counter} · ${st.reason}${st.reject ? " · reject gate fired" : ""}${
                st.defect_count > 0 ? ` · ${st.defect_count} defect(s)` : ""
              }${st.view_count > 1 ? ` · ${st.view_count} cameras` : ""}`}
        </span>
        <span className="muted" style={{ fontSize: 11, marginLeft: "auto" }}>
          dashboard ↔ backend {pollBeat % 2 ? "•" : "◦"}
        </span>
      </div>

      {log.length > 0 && (
        <div className="stack" style={{ gap: 4, marginTop: 12 }}>
          {log.map((r) => (
            <div key={r.counter} className="row" style={{ gap: 8, fontSize: 12 }}>
              <span className="muted" style={{ minWidth: 68 }}>{r.at}</span>
              <span className={"verdict " + (r.verdict === "IDLE" ? "REVIEW" : r.verdict)}>
                {r.verdict}
              </span>
              <span className="muted">
                #{r.counter} {r.reason}
                {r.reject && " · servo"}
              </span>
            </div>
          ))}
        </div>
      )}

      {err && <div className="notice err" style={{ marginTop: 10 }}>{err}</div>}
    </div>
  );
}
