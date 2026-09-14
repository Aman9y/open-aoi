import type { InspectionStatus } from "../types";

const ICON: Record<InspectionStatus, string> = {
  GOOD: "✓",
  DEFECTIVE: "✕",
  REVIEW: "!",
};

export function StatusBadge({ status }: { status: InspectionStatus }) {
  return (
    <span className={"badge " + status}>
      <span>{ICON[status]}</span> {status}
    </span>
  );
}
