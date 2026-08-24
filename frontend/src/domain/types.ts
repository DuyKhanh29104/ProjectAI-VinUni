export type Role = "reviewer" | "annotator" | "admin";

export type DatasetFormat = "KITTI" | "nuScenes";

export type ReviewStatus =
  | "unreviewed"
  | "in_review"
  | "confirmed"
  | "corrected"
  | "rejected"
  | "skipped";

export type Severity = "low" | "medium" | "high" | "critical";

export type FindingType =
  | "box_misalignment"
  | "wrong_class"
  | "missing_object"
  | "duplicate_annotation"
  | "track_id_switch"
  | "track_break"
  | "temporal_inconsistency";

export type AnnotationLayer = "original" | "proposed" | "approved";

export type AnnotationSource = "human" | "model" | "agent";

export type EvidenceKind = "geometry" | "model" | "temporal" | "context";

export type QaRunStatus = "idle" | "running" | "completed";

export type DemoMode = "ready" | "loading" | "empty" | "error" | "success" | "rejected";

export type ReviewAction =
  | "start_review"
  | "confirm"
  | "approve_correction"
  | "edit_annotation"
  | "annotator_feedback"
  | "reject_finding"
  | "skip"
  | "assign";

export interface Dataset {
  id: string;
  name: string;
  format: DatasetFormat;
  version: string;
  description: string;
  sceneCount: number;
  frameCount: number;
  annotationCount: number;
  anonymized: boolean;
}

export interface Scene {
  id: string;
  datasetId: string;
  name: string;
  sequenceLength: number;
  location: string;
  weather: string;
  annotatorId: string;
}

export interface Frame {
  id: string;
  sceneId: string;
  frameNumber: number;
  timestampMs: number;
  thumbnailUrl: string;
  width: number;
  height: number;
  anonymized: boolean;
}

export interface BoundingBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface AnnotationAttributes {
  occluded?: boolean;
  truncated?: boolean;
  visibility?: number;
  sourceNote?: string;
  deleted?: boolean;
}

export interface AnnotationRecord {
  id: string;
  sourceAnnotationId?: string;
  sourceFindingId?: string;
  frameId: string;
  trackId?: string;
  label: string;
  bbox: BoundingBox;
  attributes: AnnotationAttributes;
  layer: AnnotationLayer;
  source: AnnotationSource;
  version: number;
  updatedAt: string;
  updatedBy: string;
}

export interface PredictionRecord {
  id: string;
  frameId: string;
  trackId?: string;
  label: string;
  bbox: BoundingBox;
  confidence: number;
  modelVersion: string;
}

export interface Evidence {
  id: string;
  kind: EvidenceKind;
  metric: string;
  value: number | string;
  threshold?: string;
  description: string;
}

export interface Finding {
  id: string;
  datasetId: string;
  datasetVersion: string;
  qaRunId: string;
  frameId: string;
  sceneId: string;
  annotationId?: string;
  trackId?: string;
  type: FindingType;
  severity: Severity;
  riskScore: number;
  priority: number;
  status: ReviewStatus;
  title: string;
  summary: string;
  explanation: string;
  recommendation: string;
  evidenceIds: string[];
  createdAt: string;
  updatedAt: string;
  assigneeId?: string;
  modelVersion: string;
  ruleVersion: string;
}

export interface ReviewDecision {
  id: string;
  findingId: string;
  action: ReviewAction;
  userId: string;
  timestamp: string;
  reason?: string;
  changeSummary?: string;
  fromStatus: ReviewStatus;
  toStatus: ReviewStatus;
}

export interface User {
  id: string;
  name: string;
  email: string;
  role: Role;
  avatarInitials: string;
}

export interface ReportMetrics {
  totalAnnotations: number;
  flaggedAnnotations: number;
  reviewedCases: number;
  correctedCases: number;
  precision: number;
  recall: number;
  f1Score: number;
  falsePositiveRate: number;
  averageReviewSeconds: number;
  savedReviewHours: number;
  beforeQaErrorRate: number;
  afterQaErrorRate: number;
}

export interface QaRun {
  id: string;
  datasetId: string;
  status: QaRunStatus;
  progress: number;
  processedFrames: number;
  totalFrames: number;
  startedAt?: string;
  completedAt?: string;
  durationSeconds?: number;
  modelVersion: string;
  ruleVersion: string;
}

export interface RuleConfig {
  id: string;
  name: string;
  category: "geometry" | "temporal" | "context" | "model";
  description: string;
  enabled: boolean;
  threshold: number;
  unit: string;
  min: number;
  max: number;
  step: number;
}

export interface ModelConfig {
  id: string;
  name: string;
  version: string;
  task: string;
  enabled: boolean;
  confidenceThreshold: number;
}

export interface MockState {
  datasets: Dataset[];
  scenes: Scene[];
  frames: Frame[];
  annotations: AnnotationRecord[];
  predictions: PredictionRecord[];
  evidences: Evidence[];
  findings: Finding[];
  reviewDecisions: ReviewDecision[];
  users: User[];
  reportMetrics: ReportMetrics;
  qaRun: QaRun;
  rules: RuleConfig[];
  models: ModelConfig[];
  activeRole: Role;
  activeUserId: string;
  selectedDatasetId: string;
  lastUpdatedAt: string;
}
