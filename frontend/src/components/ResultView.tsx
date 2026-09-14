import { useState } from "react";
import type { InspectionResult } from "../types";
import { DefectList } from "./DefectList";

type ImgKey = "annotated" | "original" | "cropped" | "aligned";

const MARK: Record<string, string> = { GOOD: "✓", DEFECTIVE: "✕", REVIEW: "!" };

export function ResultView({ result }: { result: InspectionResult }) {
  const [tab, setTab] = useState<ImgKey>("annotated");
  const images: Record<ImgKey, string> = {
    annotated: result.annotated_image_path,
    original: result.original_image_path,
    cropped: result.cropped_image_path,
    aligned: result.aligned_image_path,
  };
  const src = images[tab] || images.original;

  return (
    <div>
      <div className={"verdict-banner " + result.status}>
        <div className="mark">{MARK[result.status]}</div>
        <div>
          <div className="word">{result.status}</div>
          <div className="why">{result.explanation}</div>
        </div>
      </div>

      <div className="grid-2">
        <div>
          <div className="image-tabs">
            {(["annotated", "original", "cropped", "aligned"] as ImgKey[]).map((k) => (
              <button
                key={k}
                className={tab === k ? "active" : ""}
                disabled={!images[k]}
                onClick={() => setTab(k)}
              >
                {k}
              </button>
            ))}
          </div>
          <div className="image-frame">
            {src ? <img src={src} alt={tab} /> : <span className="muted">no image</span>}
          </div>
        </div>

        <div className="stack">
          <dl className="kv">
            <dt>Result</dt>
            <dd className={"verdict " + result.status}>{result.status}</dd>
            <dt>Reason</dt>
            <dd>{result.reason}</dd>
            <dt>Confidence</dt>
            <dd>{(result.overall_confidence * 100).toFixed(1)}%</dd>
            <dt>Inspection time</dt>
            <dd>{result.inspection_time_ms} ms</dd>
            <dt>Reference</dt>
            <dd>
              {result.reference_id}{" "}
              <span className={"pill " + result.profile_kind}>{result.profile_kind}</span>
            </dd>
            <dt>Timestamp</dt>
            <dd>{new Date(result.timestamp).toLocaleString()}</dd>
            <dt>Board detect</dt>
            <dd>
              {result.detection.found
                ? `${result.detection.method} · ${(result.detection.coverage * 100).toFixed(0)}% of frame`
                : "not cropped (" + (result.detection.note || "full frame") + ")"}
            </dd>
            <dt>Alignment</dt>
            <dd>
              {result.alignment.success
                ? `ok · err ${result.alignment.alignment_error_px}px · rot ${result.alignment.rotation_deg}° · SSIM ${result.board_similarity}`
                : `FAILED — ${result.alignment.reason}`}
            </dd>
            <dt>Image quality</dt>
            <dd>{result.quality.passed ? "ok" : result.quality.issues.join("; ")}</dd>
            <dt>Model</dt>
            <dd>
              {result.model_status === "YOLO_ACTIVE"
                ? `YOLO active · ${result.detections.length} detections`
                : result.model_status === "MODEL NOT CONFIGURED"
                  ? "MODEL NOT CONFIGURED"
                  : "deterministic only"}
            </dd>
          </dl>

          <div>
            <h4 style={{ margin: "4px 0 10px" }}>
              Detected defects ({result.defects.length})
            </h4>
            <DefectList defects={result.defects} />
          </div>
        </div>
      </div>
    </div>
  );
}
