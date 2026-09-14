import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import type { AnyResult, HistoryRow, InspectionStatus } from "../types";
import { isMulti } from "../types";
import { StatusBadge } from "../components/StatusBadge";
import { ResultView } from "../components/ResultView";
import { MultiViewResultView } from "../components/MultiViewResultView";

const STATUSES: (InspectionStatus | "")[] = ["", "GOOD", "DEFECTIVE", "REVIEW"];

export function HistoryPage() {
  const [rows, setRows] = useState<HistoryRow[]>([]);
  const [status, setStatus] = useState<InspectionStatus | "">("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [detail, setDetail] = useState<AnyResult | null>(null);
  const [err, setErr] = useState("");

  const params = useCallback((): Record<string, string> => {
    const p: Record<string, string> = {};
    if (status) p.status = status;
    if (from) p.date_from = from;
    if (to) p.date_to = to + "T23:59:59";
    return p;
  }, [status, from, to]);

  const load = useCallback(() => {
    api
      .history(params())
      .then(setRows)
      .catch((e) => setErr(String(e.message ?? e)));
  }, [params]);

  useEffect(() => {
    load();
  }, [load]);

  const open = (id: string) => {
    api.getInspection(id).then(setDetail).catch((e) => setErr(String(e.message ?? e)));
  };

  return (
    <>
      <h1 className="page-title">Inspection History</h1>
      <p className="page-sub">{rows.length} record(s)</p>

      <div className="panel" style={{ marginBottom: 16 }}>
        <div className="row">
          <label className="field">
            Result
            <select value={status} onChange={(e) => setStatus(e.target.value as InspectionStatus | "")}>
              {STATUSES.map((s) => (
                <option key={s} value={s}>
                  {s || "All"}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            From
            <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
          </label>
          <label className="field">
            To
            <input type="date" value={to} onChange={(e) => setTo(e.target.value)} />
          </label>
          <a className="btn secondary" href={api.csvUrl(params())} style={{ alignSelf: "end" }}>
            Export CSV
          </a>
        </div>
      </div>

      {err && <div className="notice err">{err}</div>}

      <div className="panel table-wrap" style={{ padding: 0 }}>
        <table>
          <thead>
            <tr>
              <th className="mono">ID</th>
              <th>Time</th>
              <th>Reference</th>
              <th>Kind</th>
              <th>Result</th>
              <th>Defects</th>
              <th>Confidence</th>
              <th>Time (ms)</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.inspection_id} onClick={() => open(r.inspection_id)}>
                <td className="mono">{r.inspection_id}</td>
                <td>{new Date(r.timestamp).toLocaleString()}</td>
                <td>{r.reference_id}</td>
                <td>{r.profile_kind}</td>
                <td>
                  <StatusBadge status={r.status} />
                </td>
                <td>{r.defect_count}</td>
                <td className="mono">{(r.overall_confidence * 100).toFixed(0)}%</td>
                <td className="mono">{r.inspection_time_ms}</td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={8} className="muted" style={{ padding: 20 }}>
                  No inspections match the current filter.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {detail && (
        <div className="overlay" onClick={() => setDetail(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <button className="close" onClick={() => setDetail(null)}>
              ×
            </button>
            <h3 style={{ marginTop: 0 }}>{detail.inspection_id}</h3>
            {isMulti(detail) ? (
              <MultiViewResultView result={detail} />
            ) : (
              <ResultView result={detail} />
            )}
          </div>
        </div>
      )}
    </>
  );
}
