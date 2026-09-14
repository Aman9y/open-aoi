import type { Defect } from "../types";

const LABEL: Record<string, string> = {
  MISSING_COMPONENT: "Missing Component",
  SHIFTED_COMPONENT: "Position Deviation",
  ROTATED_COMPONENT: "Rotation Deviation",
  SIZE_DEVIATION: "Size Deviation",
  VISUAL_ANOMALY: "Visual Anomaly",
  WRONG_COMPONENT: "Wrong Component",
  UNEXPECTED_COMPONENT: "Unexpected Component",
};

export function DefectList({ defects }: { defects: Defect[] }) {
  if (defects.length === 0)
    return <div className="notice info">No defects detected.</div>;

  return (
    <div className="stack">
      {defects.map((d, i) => (
        <div className="defect" key={i}>
          <div className="head">
            <span className="comp">{d.component}</span>
            <span className="type">{LABEL[d.type] ?? d.type}</span>
            <span className="conf">{(d.confidence * 100).toFixed(1)}%</span>
          </div>
          <dl>
            <dt>Expected</dt>
            <dd>{d.expected}</dd>
            <dt>Observed</dt>
            <dd>{d.observed}</dd>
            {d.deviation_px != null && (
              <>
                <dt>Deviation</dt>
                <dd>
                  {d.deviation_px.toFixed(1)} px
                  {d.deviation_mm != null && ` (${d.deviation_mm.toFixed(2)} mm)`}
                  {d.allowed_px != null && ` · allowed ${d.allowed_px.toFixed(1)} px`}
                </dd>
              </>
            )}
            {d.rotation_deg != null && (
              <>
                <dt>Rotation</dt>
                <dd>
                  {d.rotation_deg.toFixed(1)}°
                  {d.allowed_rotation_deg != null &&
                    ` · allowed ±${d.allowed_rotation_deg.toFixed(1)}°`}
                </dd>
              </>
            )}
          </dl>
        </div>
      ))}
    </div>
  );
}
