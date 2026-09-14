import { useState } from "react";
import type { MultiViewResult } from "../types";
import { ResultView } from "./ResultView";
import { StatusBadge } from "./StatusBadge";

const MARK: Record<string, string> = { GOOD: "✓", DEFECTIVE: "✕", REVIEW: "!" };

export function MultiViewResultView({ result }: { result: MultiViewResult }) {
  const [open, setOpen] = useState<string | null>(
    result.views.find((v) => v.result.status !== "GOOD")?.name ?? null,
  );

  return (
    <div>
      <div className={"verdict-banner " + result.status}>
        <div className="mark">{MARK[result.status]}</div>
        <div>
          <div className="word">{result.status}</div>
          <div className="why">{result.explanation}</div>
        </div>
      </div>

      <dl className="kv" style={{ marginBottom: 16 }}>
        <dt>Cameras</dt>
        <dd>{result.view_count}</dd>
        <dt>Combined confidence</dt>
        <dd>{(result.overall_confidence * 100).toFixed(1)}%</dd>
        <dt>Total time</dt>
        <dd>{result.inspection_time_ms} ms</dd>
        <dt>References</dt>
        <dd>{result.reference_id}</dd>
      </dl>

      {result.montage_image_path && (
        <div className="image-frame" style={{ marginBottom: 16 }}>
          <img src={result.montage_image_path} alt="all views" />
        </div>
      )}

      <div className="stack">
        {result.views.map((v) => (
          <div className="panel" key={v.name} style={{ padding: 0 }}>
            <button
              className="between"
              onClick={() => setOpen(open === v.name ? null : v.name)}
              style={{
                width: "100%",
                background: "none",
                border: "none",
                color: "var(--text)",
                padding: "14px 16px",
                cursor: "pointer",
                font: "inherit",
              }}
            >
              <span className="row" style={{ gap: 10 }}>
                <strong style={{ fontFamily: "var(--mono)" }}>{v.name}</strong>
                <StatusBadge status={v.result.status} />
                <span className="muted" style={{ fontSize: 12 }}>
                  {v.result.reference_id} · {v.result.defects.length} defect(s)
                </span>
              </span>
              <span className="muted">{open === v.name ? "▾" : "▸"}</span>
            </button>
            {open === v.name && (
              <div style={{ padding: "0 16px 16px", borderTop: "1px solid var(--border)" }}>
                <div style={{ height: 12 }} />
                <ResultView result={v.result} />
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
