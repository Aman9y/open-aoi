import type {
  AnyResult,
  HistoryRow,
  InspectionResult,
  MultiViewResult,
  Reference,
  StationState,
  Stats,
} from "./types";

async function j<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      /* keep statusText */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => fetch("/api/health").then((r) => j<{ status: string; yolo: string }>(r)),

  listReferences: () => fetch("/api/references").then((r) => j<Reference[]>(r)),

  activeReference: () =>
    fetch("/api/references/active").then((r) => j<Reference | null>(r)),

  activateReference: (id: string) =>
    fetch(`/api/references/${id}/activate`, { method: "POST" }).then((r) =>
      j<Reference>(r),
    ),

  deleteReference: (id: string) =>
    fetch(`/api/references/${id}`, { method: "DELETE" }).then((r) => {
      if (!r.ok && r.status !== 204) throw new Error("delete failed");
    }),

  createReference: (form: FormData) =>
    fetch("/api/references", { method: "POST", body: form }).then((r) =>
      j<Reference>(r),
    ),

  captureReference: (body: {
    id: string;
    name: string;
    source: string;
    kind?: string;
    inspection_mode?: "regions" | "surface";
    mm_per_px?: number | null;
    activate?: boolean;
  }) =>
    fetch("/api/references/capture", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then((r) => j<Reference>(r)),

  inspect: (file: File, referenceId?: string, save = true) => {
    const form = new FormData();
    form.append("file", file);
    if (referenceId) form.append("reference_id", referenceId);
    form.append("save", String(save));
    return fetch("/api/inspections/inspect", { method: "POST", body: form }).then(
      (r) => j<InspectionResult>(r),
    );
  },

  inspectLive: (source: string, referenceId?: string, save = true) =>
    fetch("/api/inspections/inspect_live", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source, reference_id: referenceId ?? null, save }),
    }).then((r) => j<InspectionResult>(r)),

  inspectMulti: (
    views: { name: string; source: string; reference_id?: string }[],
    save = true,
  ) =>
    fetch("/api/inspections/inspect_multi", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ views, save }),
    }).then((r) => j<MultiViewResult>(r)),

  cameraDevices: () =>
    fetch("/api/camera/devices").then((r) =>
      j<{ source: string; label: string; width: number; height: number }[]>(r),
    ),

  cameraPreviewUrl: (source: string) =>
    `/api/camera/preview?source=${encodeURIComponent(source)}`,

  stationState: () => fetch("/api/station/state").then((r) => j<StationState>(r)),

  stationTrigger: () =>
    fetch("/api/station/trigger", { method: "POST" }).then((r) => j<InspectionResult>(r)),

  getInspection: (id: string) =>
    fetch(`/api/inspections/${id}`).then((r) => j<AnyResult>(r)),

  history: (params: Record<string, string>) => {
    const qs = new URLSearchParams(params).toString();
    return fetch(`/api/inspections?${qs}`).then((r) => j<HistoryRow[]>(r));
  },

  stats: (dateFrom?: string) => {
    const qs = dateFrom ? `?date_from=${encodeURIComponent(dateFrom)}` : "";
    return fetch(`/api/stats${qs}`).then((r) => j<Stats>(r));
  },

  csvUrl: (params: Record<string, string>) =>
    `/api/inspections.csv?${new URLSearchParams(params).toString()}`,
};
