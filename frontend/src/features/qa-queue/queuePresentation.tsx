import type { ReactNode } from "react";

import { Card } from "../../components/ui";
import type { FindingType, ReviewStatus, Severity } from "../../domain/types";

export const findingTypeLabels: Record<FindingType, string> = {
  box_misalignment: "Box lệch vị trí",
  wrong_class: "Sai class",
  missing_object: "Thiếu object",
  duplicate_annotation: "Annotation trùng",
  track_id_switch: "ID tracking không nhất quán",
  track_break: "Track bị đứt",
  temporal_inconsistency: "Không nhất quán thời gian",
};

export const statusLabels: Record<ReviewStatus, string> = {
  unreviewed: "Chờ review",
  in_review: "Đang review",
  confirmed: "Đã xác nhận",
  corrected: "Đã sửa",
  rejected: "Bác bỏ",
  skipped: "Tạm hoãn",
};

export const reviewStatuses: ReviewStatus[] = [
  "unreviewed",
  "in_review",
  "confirmed",
  "corrected",
  "rejected",
  "skipped",
];

export const chartColors = ["#7667e8", "#db6b78", "#9385f2", "#dca45f", "#4dbb8b"];

export function donutBackground(items: Array<{ count: number }>): string {
  if (items.length === 0) return "conic-gradient(#282c35 0 100%)";
  const total = items.reduce((sum, item) => sum + item.count, 0) || 1;
  let cursor = 0;
  const segments = items.map((item, index) => {
    const start = cursor;
    cursor += (item.count / total) * 100;
    return `${chartColors[index % chartColors.length]} ${start}% ${cursor}%`;
  });
  return `conic-gradient(${segments.join(", ")})`;
}

export function priorityLabel(priority: Severity): string {
  if (priority === "critical") return "Khẩn cấp";
  if (priority === "high") return "Cao";
  if (priority === "medium") return "Trung bình";
  return "Thấp";
}

export function QueueKpiCard({
  icon,
  label,
  value,
  detail,
  tone,
}: {
  icon: string;
  label: string;
  value: string | number;
  detail: string;
  tone: "blue" | "red" | "purple" | "green" | "orange";
}) {
  return (
    <Card className={`queue-kpi-card queue-kpi-${tone}`}>
      <div><span>{label}</span><strong>{value}</strong><small>{detail}</small></div>
      <i aria-hidden="true">{icon}</i>
    </Card>
  );
}

export function QueuePageState({
  title,
  detail,
  action,
  error = false,
}: {
  title: string;
  detail: string;
  action?: ReactNode;
  error?: boolean;
}) {
  return (
    <div className="page-container queue-console-page">
      <Card className={`api-queue-page-state ${error ? "is-error" : ""}`} role={error ? "alert" : "status"}>
        <span aria-hidden="true">{error ? "!" : "◎"}</span>
        <strong>{title}</strong>
        <p>{detail}</p>
        {action}
      </Card>
    </div>
  );
}
