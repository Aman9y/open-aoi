import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import type { HistoryRow, Stats } from "../types";

const DEFECT_LABEL: Record<string, string> = {
  MISSING_COMPONENT: "Missing component",
  SHIFTED_COMPONENT: "Position error",
  ROTATED_COMPONENT: "Rotation error",
  VISUAL_ANOMALY: "Visual anomaly",
  SIZE_DEVIATION: "Size deviation",
};

export function AnalyticsPage() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [rows, setRows] = useState<HistoryRow[]>([]);
  const [reasons, setReasons] = useState<Record<string, number>>({});

  useEffect(() => {
    api.stats().then(setStats).catch(() => {});
    api.history({ limit: "1000" }).then(async (hist) => {
      setRows(hist);
      // Reason codes are a cheap proxy for defect mix without fetching every result.
      const counts: Record<string, number> = {};
      hist.forEach((r) => {
        if (r.status === "DEFECTIVE") counts[r.reason] = (counts[r.reason] ?? 0) + 1;
      });
      setReasons(counts);
      void DEFECT_LABEL;
    });
  }, []);

  const defectRate = useMemo(() => {
    if (!stats || stats.total === 0) return 0;
    return (stats.defective / stats.total) * 100;
  }, [stats]);

  const reasonTotal = Object.values(reasons).reduce((a, b) => a + b, 0);

  return (
    <>
      <h1 className="page-title">Analytics</h1>
      <p className="page-sub">All recorded inspections</p>

      <div className="tiles" style={{ marginBottom: 18 }}>
        <div className="tile">
          <div className="n">{stats?.total ?? "–"}</div>
          <div className="l">Inspections</div>
        </div>
        <div className="tile good">
          <div className="n">{stats?.good ?? "–"}</div>
          <div className="l">GOOD</div>
        </div>
        <div className="tile bad">
          <div className="n">{stats?.defective ?? "–"}</div>
          <div className="l">DEFECTIVE</div>
        </div>
        <div className="tile review">
          <div className="n">{stats?.review ?? "–"}</div>
          <div className="l">REVIEW</div>
        </div>
      </div>

      <div className="grid-2">
        <div className="panel">
          <h4 style={{ marginTop: 0 }}>Key metrics</h4>
          <dl className="kv">
            <dt>Defect rate</dt>
            <dd>{defectRate.toFixed(1)}%</dd>
            <dt>Avg inspection time</dt>
            <dd>{stats ? (stats.avg_time_ms / 1000).toFixed(2) : "–"} s</dd>
            <dt>Review rate</dt>
            <dd>
              {stats && stats.total
                ? ((stats.review / stats.total) * 100).toFixed(1)
                : "0.0"}
              %
            </dd>
          </dl>
          <p className="muted" style={{ fontSize: 12, marginBottom: 0 }}>
            A DEFECTIVE board that reads GOOD (false accept) is the critical error class —
            tracked explicitly in the evaluation report, not here.
          </p>
        </div>

        <div className="panel">
          <h4 style={{ marginTop: 0 }}>Defective — reason distribution</h4>
          {reasonTotal === 0 && <div className="muted">No defective inspections yet.</div>}
          {Object.entries(reasons)
            .sort((a, b) => b[1] - a[1])
            .map(([reason, n]) => (
              <div className="bar-row" key={reason}>
                <span>{reason}</span>
                <span className="bar-track">
                  <span
                    className="bar-fill"
                    style={{ width: `${(n / reasonTotal) * 100}%` }}
                  />
                </span>
                <span className="mono">{((n / reasonTotal) * 100).toFixed(0)}%</span>
              </div>
            ))}
        </div>
      </div>

      <div className="panel" style={{ marginTop: 18 }}>
        <h4 style={{ marginTop: 0 }}>Recent throughput</h4>
        <div className="muted" style={{ fontSize: 12 }}>
          {rows.length} inspections loaded ·{" "}
          {rows.filter((r) => r.status === "DEFECTIVE").length} defective ·{" "}
          {rows.filter((r) => r.status === "REVIEW").length} review
        </div>
      </div>
    </>
  );
}
