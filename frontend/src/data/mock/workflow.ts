import type {
  FeedbackComment,
  ModelConfig,
  QaRun,
  ReportMetrics,
  RuleConfig,
  User,
  WorkBatch,
} from "../../domain/types.ts";

export const mockBatches: WorkBatch[] = [
  {
    id: "batch-kitti-urban-aug",
    datasetId: "dataset-kitti-demo",
    name: "Urban traffic · August",
    customerName: "Mobility Lab",
    state: "review",
    frameCount: 480,
    assignedCount: 480,
    submittedCount: 436,
    approvedCount: 392,
    ownerId: "user-reviewer",
    dueAt: "2026-08-30T10:00:00.000Z",
    createdAt: "2026-08-20T09:00:00.000Z",
  },
  {
    id: "batch-nuscenes-night-aug",
    datasetId: "dataset-nuscenes-demo",
    name: "Night scenes · Calibration",
    customerName: "Perception Research",
    state: "active",
    frameCount: 220,
    assignedCount: 180,
    submittedCount: 94,
    approvedCount: 62,
    ownerId: "user-reviewer",
    dueAt: "2026-09-02T10:00:00.000Z",
    createdAt: "2026-08-23T09:00:00.000Z",
  },
];

export const mockFeedbackComments: FeedbackComment[] = [
  {
    id: "comment-001",
    findingId: "finding-006",
    authorId: "user-reviewer",
    targetType: "frame",
    targetId: "frame-highway-003",
    reasonCategory: "missing_label",
    body: "Kiểm tra vùng khuất bên phải và bổ sung object nếu xuất hiện ở hai frame liền kề.",
    blocking: true,
    resolved: false,
    annotationRevision: 1,
    createdAt: "2026-08-25T08:40:00.000Z",
  },
];

export const mockUsers: User[] = [
  {
    id: "user-reviewer",
    name: "Minh Trần",
    email: "minh.reviewer@labelguardian.local",
    role: "reviewer",
    avatarInitials: "MT",
  },
  {
    id: "user-annotator",
    name: "Lan Nguyễn",
    email: "lan.annotator@labelguardian.local",
    role: "annotator",
    avatarInitials: "LN",
  },
  {
    id: "user-admin",
    name: "Quang Phạm",
    email: "quang.admin@labelguardian.local",
    role: "admin",
    avatarInitials: "QP",
  },
];

export const mockReportMetrics: ReportMetrics = {
  totalAnnotations: 22,
  flaggedAnnotations: 6,
  reviewedCases: 3,
  correctedCases: 0,
  precision: 0.84,
  recall: 0.79,
  f1Score: 0.81,
  falsePositiveRate: 0.16,
  averageReviewSeconds: 42,
  savedReviewHours: 3.6,
  beforeQaErrorRate: 0.18,
  afterQaErrorRate: 0.07,
};

export const mockQaRun: QaRun = {
  id: "qa-run-demo-001",
  datasetId: "dataset-kitti-demo",
  status: "idle",
  progress: 0,
  processedFrames: 0,
  totalFrames: 6,
  modelVersion: "yolo-reference@2026.08",
  ruleVersion: "geometry + temporal + context@0.5",
};

export const mockRules: RuleConfig[] = [
  {
    id: "rule-box-iou",
    name: "Box alignment / IoU",
    category: "geometry",
    description:
      "Gắn cờ khi IoU giữa annotation và prediction thấp hơn ngưỡng.",
    enabled: true,
    threshold: 0.5,
    unit: "IoU tối thiểu",
    min: 0.1,
    max: 0.95,
    step: 0.05,
  },
  {
    id: "rule-track-gap",
    name: "Track continuity gap",
    category: "temporal",
    description:
      "Phát hiện track bị đứt khi khoảng cách frame vượt quá ngưỡng.",
    enabled: true,
    threshold: 2,
    unit: "frame tối đa",
    min: 1,
    max: 8,
    step: 1,
  },
  {
    id: "rule-context-match",
    name: "Context consistency",
    category: "context",
    description: "So sánh class và context giữa các frame lân cận.",
    enabled: true,
    threshold: 0.7,
    unit: "điểm tối thiểu",
    min: 0.1,
    max: 0.99,
    step: 0.05,
  },
  {
    id: "rule-model-gap",
    name: "Model confidence gap",
    category: "model",
    description: "Gắn cờ khi model có confidence cao nhưng khác nhãn gốc.",
    enabled: false,
    threshold: 0.2,
    unit: "chênh lệch tối thiểu",
    min: 0.05,
    max: 0.8,
    step: 0.05,
  },
];

export const mockModels: ModelConfig[] = [
  {
    id: "model-yolo-reference",
    name: "YOLO reference",
    version: "yolo-reference@2026.08",
    task: "Object detection",
    enabled: true,
    confidenceThreshold: 0.65,
  },
  {
    id: "model-tracker-reference",
    name: "Tracker reference",
    version: "tracker-reference@2026.08",
    task: "Multi-object tracking",
    enabled: true,
    confidenceThreshold: 0.7,
  },
];
