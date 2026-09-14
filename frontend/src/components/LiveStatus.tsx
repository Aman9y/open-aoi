import { useEffect, useState } from "react";
import type { InspectionResult } from "../types";

const DEFECT_LABEL: Record<string, string> = {
  MISSING_COMPONENT: "Missing",
  SHIFTED_COMPONENT: "Shifted",
  ROTATED_COMPONENT: "Rotated",
  WRONG_COMPONENT: "Wrong part",
  UNEXPECTED_COMPONENT: "Unexpected",
  VISUAL_ANOMALY: "Anomaly",
  SIZE_DEVIATION: "Size",
};

export function LiveStatus({
  result,
  updatedAt,
  running,
}: {
  result: InspectionResult | null;
  updatedAt: number;
  running: boolean;
}) {
  const [, tick] = useState(0);
  useEffect(() => {
    const t = setInterval(() => tick((n) => n + 1), 1000);
    return () => clearInterval(t);
  }, []);

  const age = updatedAt ? Math.max(0, Math.round((Date.now() - updatedAt) / 1000)) : null;

  return (
    <div className="panel stack" style={{ minWidth: 260 }}>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <span className="muted" style={{ fontSize: 12 }}>
          LIVE {running ? <span className="dot" style={{ display: "inline-block" }} /> : "· paused"}
        </span>
        {age != null && (
          <span className="muted" style={{ fontSize: 12 }}>
            {age === 0 ? "just now" : `${age}s ago`}
          </span>
        )}
      </div>

      {!result ? (
        <div className="verdict REVIEW" style={{ fontSize: 24 }}>
          {running ? "…" : "—"}
        </div>
      ) : (
        <>
          <div className={"verdict " + result.status} style={{ fontSize: 30, margin: 0 }}>
            {result.status}
          </div>
          <div className="muted" style={{ fontSize: 12 }}>
            {result.reason} · {(result.overall_confidence * 100).toFixed(0)}% ·{" "}
            {result.inspection_time_ms} ms
            {result.model_status === "YOLO_ACTIVE" && " · YOLO"}
          </div>
          {result.defects.length > 0 && (
            <div className="stack" style={{ gap: 6 }}>
              {result.defects.map((d, i) => (
                <div key={i} className="row" style={{ gap: 8, fontSize: 13 }}>
                  <span className="comp" style={{ fontFamily: "var(--mono)", minWidth: 46 }}>
                    {d.component}
                  </span>
                  <span style={{ color: "var(--bad)" }}>
                    {DEFECT_LABEL[d.type] ?? d.type}
                  </span>
                  <span className="muted">{(d.confidence * 100).toFixed(0)}%</span>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
