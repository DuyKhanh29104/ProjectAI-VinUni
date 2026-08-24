import type { ReviewStatus, Role } from "../domain/types";

export interface AppRouteDefinition {
  id: string;
  label: string;
  path: string;
  description: string;
  phase: "foundation" | "next";
  allowedRoles: Role[];
}

export const appRoutes: AppRouteDefinition[] = [
  {
    id: "overview",
    label: "Tổng quan QA",
    path: "/",
    description: "KPI, mức độ rủi ro và tình hình review dataset.",
    phase: "next",
    allowedRoles: ["reviewer", "annotator", "admin"],
  },
  {
    id: "qa-queue",
    label: "QA Queue",
    path: "/qa-queue",
    description: "Chọn dữ liệu thật và chạy Agent QA theo frame.",
    phase: "next",
    allowedRoles: ["reviewer", "admin"],
  },
  {
    id: "qa-cases",
    label: "QA Cases",
    path: "/qa-cases",
    description: "Danh sách finding do Agent tạo, tách biệt khỏi hàng đợi chạy QA.",
    phase: "next",
    allowedRoles: ["reviewer", "annotator", "admin"],
  },
  {
    id: "case-detail",
    label: "Case review",
    path: "/cases/:findingId",
    description: "Frame viewer, sequence, agent evidence và thao tác phê duyệt.",
    phase: "next",
    allowedRoles: ["reviewer", "annotator", "admin"],
  },
  {
    id: "annotator-workspace",
    label: "2D Editor",
    path: "/editor",
    description: "Công cụ chính để chỉnh sửa, lưu revision và khôi phục nhãn 2D.",
    phase: "next",
    allowedRoles: ["reviewer", "annotator", "admin"],
  },
  {
    id: "reports",
    label: "Báo cáo",
    path: "/reports",
    description: "Metrics phát hiện lỗi và hiệu quả vận hành QA.",
    phase: "next",
    allowedRoles: ["reviewer", "admin"],
  },
  {
    id: "dataset-run",
    label: "Datasets / Runs",
    path: "/dataset-runs",
    description: "Dataset version, phạm vi frame và tiến trình QA run mock.",
    phase: "next",
    allowedRoles: ["reviewer", "admin"],
  },
  {
    id: "pipeline",
    label: "Pipeline",
    path: "/pipeline",
    description: "Cloud ingestion runs, stage progress và pipeline logs.",
    phase: "next",
    allowedRoles: ["reviewer", "admin"],
  },
  {
    id: "settings",
    label: "Cấu hình",
    path: "/settings",
    description: "Dataset version, rule threshold, model version và user mock.",
    phase: "next",
    allowedRoles: ["admin"],
  },
];

export const reviewWorkflow: Array<{
  status: ReviewStatus;
  label: string;
  description: string;
}> = [
  {
    status: "unreviewed",
    label: "Chưa review",
    description: "Agent đã gắn cờ, chưa có quyết định của con người.",
  },
  {
    status: "in_review",
    label: "Đang review",
    description: "Reviewer đang kiểm tra evidence và sequence.",
  },
  {
    status: "confirmed",
    label: "Đã xác nhận",
    description: "Nhãn hiện tại được xác nhận là đúng.",
  },
  {
    status: "corrected",
    label: "Đã sửa",
    description: "Thay đổi đã được con người phê duyệt.",
  },
  {
    status: "rejected",
    label: "Bác bỏ",
    description: "Cảnh báo được xác định là false positive.",
  },
  {
    status: "skipped",
    label: "Bỏ qua",
    description: "Tạm hoãn xử lý và cần lưu lý do.",
  },
];

export const demoFlow = [
  "Chọn dataset version",
  "Lọc case risk cao và chưa review",
  "Mở case và xem frame/sequence",
  "Đọc evidence từ rule/model/agent",
  "Mở đúng ảnh trong 2D Editor",
  "Chỉnh sửa và lưu annotation revision",
  "Kiểm tra audit history",
  "Xuất báo cáo QA",
] as const;

export const roleLabels: Record<Role, string> = {
  reviewer: "QA Reviewer",
  annotator: "Annotator",
  admin: "Admin",
};
