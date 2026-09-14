// Mirrors backend/app/schemas — keep in sync with the Pydantic models.

export type InspectionStatus = "GOOD" | "DEFECTIVE" | "REVIEW";

export type DefectType =
  | "MISSING_COMPONENT"
  | "SHIFTED_COMPONENT"
  | "ROTATED_COMPONENT"
  | "SIZE_DEVIATION"
  | "VISUAL_ANOMALY"
  | "WRONG_COMPONENT"
  | "UNEXPECTED_COMPONENT";

export type ModelStatus =
  | "DETERMINISTIC_ONLY"
  | "MODEL NOT CONFIGURED"
  | "YOLO_ACTIVE";

export interface Defect {
  component: string;
  type: DefectType;
  confidence: number;
  expected: string;
  observed: string;
  expected_position: [number, number] | null;
  actual_position: [number, number] | null;
  deviation_px: number | null;
  deviation_mm: number | null;
  allowed_px: number | null;
  rotation_deg: number | null;
  allowed_rotation_deg: number | null;
  bbox: [number, number, number, number] | null;
}

export interface QualityReport {
  passed: boolean;
  blur_score: number;
  brightness: number;
  contrast: number;
  overexposed_frac: number;
  issues: string[];
}

export interface BoardDetection {
  found: boolean;
  method: string;
  coverage: number;
  quad: [number, number][];
  note: string;
}

export interface AlignmentMetadata {
  success: boolean;
  rotation_deg: number;
  scale: number;
  translation_px: [number, number];
  inliers: number;
  alignment_error_px: number;
  reason: string;
}

export interface RegionMeasurement {
  name: string;
  found: boolean;
  peak_corr: number;
  offset_px: number;
  rotation_deg: number;
  ssim: number;
  expected_center: [number, number];
  observed_center: [number, number] | null;
  bbox: [number, number, number, number];
  detector_class: string | null;
  detector_confidence: number | null;
  detector_agreement: "agree" | "conflict" | "absent" | null;
}

export interface ComponentDetection {
  label: string;
  confidence: number;
  bbox: [number, number, number, number];
  matched_region: string | null;
}

export type AnyResult = InspectionResult | MultiViewResult;

export function isMulti(r: AnyResult): r is MultiViewResult {
  return r.result_type === "multi";
}

export interface ViewResult {
  name: string;
  source: string;
  result: InspectionResult;
}

export interface MultiViewResult {
  result_type: "multi";
  inspection_id: string;
  timestamp: string;
  reference_id: string;
  profile_kind: string;
  status: InspectionStatus;
  reason: string;
  explanation: string;
  overall_confidence: number;
  inspection_time_ms: number;
  view_count: number;
  defects: Defect[];
  views: ViewResult[];
  montage_image_path: string;
  model_status: ModelStatus;
}

export interface InspectionResult {
  result_type: string;
  inspection_id: string;
  timestamp: string;
  reference_id: string;
  profile_kind: string;
  status: InspectionStatus;
  reason: string;
  explanation: string;
  overall_confidence: number;
  inspection_time_ms: number;
  quality: QualityReport;
  detection: BoardDetection;
  alignment: AlignmentMetadata;
  board_similarity: number;
  regions: RegionMeasurement[];
  detections: ComponentDetection[];
  defects: Defect[];
  original_image_path: string;
  cropped_image_path: string;
  aligned_image_path: string;
  annotated_image_path: string;
  montage_image_path: string;
  model_status: ModelStatus;
}

export interface Region {
  name: string;
  bbox: [number, number, number, number];
  expected_class: string | null;
  tolerances: Record<string, unknown>;
}

export interface Reference {
  id: string;
  name: string;
  kind: string;
  inspection_mode: "regions" | "surface";
  active: boolean;
  image_path: string;
  regions: Region[];
  mm_per_px: number | null;
  created_at: string;
  notes: string;
}

export interface HistoryRow {
  inspection_id: string;
  timestamp: string;
  reference_id: string;
  profile_kind: string;
  status: InspectionStatus;
  reason: string;
  overall_confidence: number;
  inspection_time_ms: number;
  defect_count: number;
}

export interface StationState {
  enabled: boolean;
  counter: number;
  view_count: number;
  verdict: "GOOD" | "DEFECTIVE" | "REVIEW" | "IDLE";
  reason: string;
  defect_count: number;
  reject: boolean;
  inspection_id: string;
  timestamp: string;
  source: string;
  esp32_online: boolean;
  esp32_last_seen_s_ago: number | null;
}

export interface Stats {
  total: number;
  avg_time_ms: number;
  good: number;
  defective: number;
  review: number;
}
