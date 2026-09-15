import type { CSSProperties } from "react";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  ChevronRight,
  CircleDot,
  Clock3,
  Database,
  GitBranch,
  Layers3,
  MessageSquareWarning,
  Monitor,
  Play,
  RefreshCw,
  ScanSearch,
  ShieldCheck,
  UserRoundCheck,
} from "lucide-react";
import { useSearchParams } from "react-router-dom";
import { isApiDataSourceEnabled } from "../api/labelGuardianApi";
import {
  useQaCasesQuery,
  useRealDatasetFrameSamplesQuery,
  usePipelineRunsQuery,
} from "../api/queries";
import { Button } from "../components/ui";
import { cloudDatasets } from "../config/cloudDataset";
import type {
  FindingType,
  MockState,
  Role,
  ReviewStatus,
  Severity,
  TaskWorkflowStage,
} from "../domain/types";
import "../styles/overview-v2.css";

const findingTypeLabels: Record<FindingType, string> = {
  box_misalignment: "Box alignment",
  wrong_class: "Class mismatch",
  missing_object: "Missing object",
  duplicate_annotation: "Duplicate label",
  track_id_switch: "Track ID switch",
  track_break: "Track break",
  temporal_inconsistency: "Temporal drift",
};

const stageLabels: Record<TaskWorkflowStage, string> = {
  unassigned: "Unassigned",
  assigned: "Assigned",
  in_progress: "In progress",
  submitted: "Submitted",
  in_review: "In review",
  changes_requested: "Changes requested",
  resubmitted: "Resubmitted",
  approved: "Approved",
};

const severityOrder: Severity[] = ["critical", "high", "medium", "low"];
const severityLabels: Record<Severity, string> = {
  critical: "Critical",
  high: "High",
  medium: "Medium",
  low: "Low",
};

const roleCopy: Record<Role, { label: string; title: string; action: string }> =
  {
    reviewer: {
      label: "QA Reviewer",
      title: "Review attention",
      action: "Start next review",
    },
    annotator: {
      label: "Annotator",
      title: "Annotation attention",
      action: "Resolve feedback",
    },
    admin: {
      label: "Admin / ML Engineer",
      title: "Agent attention",
      action: "Inspect agent signals",
    },
  };

interface OverviewTask {
  id: string;
  frameId: string;
  frameNumber?: number;
  title: string;
  type: FindingType;
  severity: Severity;
  risk: number;
  stage: TaskWorkflowStage;
  status: ReviewStatus;
  assigneeId?: string;
  ownerName: string;
  createdAt: string;
  updatedAt: string;
  thumbnailUrl?: string;
  commentCount: number;
}

interface RoleFact {
  label: string;
  value: number | string;
  tone?: "neutral" | "warning" | "danger" | "success";
}

const ageColumns = [
  { label: "< 24h", min: 0, max: 1 },
  { label: "1–3d", min: 1, max: 4 },
  { label: "4–7d", min: 4, max: 8 },
  { label: "8d+", min: 8, max: Number.POSITIVE_INFINITY },
];

function stageFromStatus(status: ReviewStatus): TaskWorkflowStage {
  if (status === "unreviewed") return "submitted";
  if (status === "in_review") return "in_review";
  return "approved";
}

function riskToSeverity(risk: number): Severity {
  if (risk >= 90) return "critical";
  if (risk >= 80) return "high";
  if (risk >= 50) return "medium";
  return "low";
}

function daysSince(timestamp: string, now: number): number {
  const parsed = Date.parse(timestamp);
  if (!Number.isFinite(parsed)) return 0;
  return Math.max(0, (now - parsed) / 86_400_000);
}

function formatAge(timestamp: string, now: number): string {
  const ageDays = daysSince(timestamp, now);
  if (ageDays < 1 / 24) return "Just now";
  if (ageDays < 1) return `${Math.max(1, Math.floor(ageDays * 24))}h`;
  return `${Math.floor(ageDays)}d`;
}

function nextActionFor(role: Role, stage: TaskWorkflowStage): string {
  if (role === "annotator") {
    if (stage === "changes_requested") return "Resolve feedback";
    if (stage === "assigned") return "Start labeling";
    if (stage === "in_progress") return "Continue labeling";
    return "View submission";
  }
  if (role === "admin") return "Inspect evidence";
  if (stage === "submitted" || stage === "resubmitted") return "Review case";
  if (stage === "in_review") return "Continue review";
  if (stage === "changes_requested") return "Monitor rework";
  return "Open case";
}

function taskIsOpen(task: OverviewTask): boolean {
  return task.stage !== "approved";
}

function taskMatchesRole(
  task: OverviewTask,
  role: Role,
  activeUserId: string,
): boolean {
  if (role === "admin") return taskIsOpen(task);
  if (role === "annotator") {
    return (
      task.assigneeId === activeUserId &&
      ["assigned", "in_progress", "changes_requested", "resubmitted"].includes(
        task.stage,
      )
    );
  }
  return (
    ["unassigned", "submitted", "in_review", "resubmitted"].includes(
      task.stage,
    ) &&
    (!task.assigneeId || task.assigneeId === activeUserId)
  );
}

function sortTasks(a: OverviewTask, b: OverviewTask): number {
  const severityDelta =
    severityOrder.indexOf(a.severity) - severityOrder.indexOf(b.severity);
  if (severityDelta !== 0) return severityDelta;
  return b.risk - a.risk || Date.parse(a.createdAt) - Date.parse(b.createdAt);
}

export function OverviewView({
  state,
  onOpenQueue,
  onOpenFinding,
}: {
  state: MockState;
  onOpenQueue: () => void;
  onOpenFinding?: (findingId: string) => void;
}) {
  const apiDataSourceEnabled = isApiDataSourceEnabled();
  const [searchParams] = useSearchParams();
  const configuredDataset = cloudDatasets[0];
  const apiDataset =
    searchParams.get("dataset") || configuredDataset?.id || "nuscenes";
  const apiSplit =
    searchParams.get("split") ||
    import.meta.env.VITE_DATASET_DEFAULT_SPLIT ||
    "product";
  const apiCasesQuery = useQaCasesQuery(
    { datasetId: apiDataset },
    apiDataSourceEnabled,
  );
  const apiSamplesQuery = useRealDatasetFrameSamplesQuery(
    apiSplit,
    0,
    apiDataset,
  );
  const apiCases = apiCasesQuery.data?.results ?? [];
  const apiSamples = apiSamplesQuery.data;
  const now = Date.now();
  const role = state.activeRole;
  const activeUser = state.users.find((user) => user.id === state.activeUserId);
  const pipelineRunsQuery = usePipelineRunsQuery(apiDataSourceEnabled);
  const latestRun = pipelineRunsQuery.data?.results?.[0];
  const realQaRunStatus = latestRun?.status ?? "idle";
  const realQaRunProgress =
    latestRun?.stages.find((s) => s.percent < 100)?.percent ??
    (latestRun?.status === "finished" ? 100 : 0);
  const realQaRunModelVersion = latestRun?.datasetType ?? "yolov8-nuscenes";
  const realQaRunRuleVersion = latestRun?.release ?? "v1.0-mini";

  const selectedDataset =
    state.datasets.find((item) => item.id === state.selectedDatasetId) ??
    state.datasets[0];
  const selectedBatch = state.batches.find(
    (batch) => batch.datasetId === state.selectedDatasetId,
  );
  const selectedSceneIds = new Set(
    state.scenes
      .filter((scene) => scene.datasetId === state.selectedDatasetId)
      .map((scene) => scene.id),
  );
  const frameById = new Map(state.frames.map((frame) => [frame.id, frame]));
  const userById = new Map(state.users.map((user) => [user.id, user]));
  const commentCountByFinding = state.feedbackComments.reduce<
    Record<string, number>
  >((counts, comment) => {
    if (!comment.resolved)
      counts[comment.findingId] = (counts[comment.findingId] ?? 0) + 1;
    return counts;
  }, {});

  const mockTasks: OverviewTask[] = state.findings
    .filter((finding) => selectedSceneIds.has(finding.sceneId))
    .map((finding) => {
      const frame = frameById.get(finding.frameId);
      return {
        id: finding.id,
        frameId: finding.frameId,
        frameNumber: frame?.frameNumber,
        title: finding.title,
        type: finding.type,
        severity: finding.severity,
        risk: Math.round(finding.riskScore * 100),
        stage: finding.workflowStage,
        status: finding.status,
        assigneeId: finding.assigneeId,
        ownerName: finding.assigneeId
          ? (userById.get(finding.assigneeId)?.name ?? finding.assigneeId)
          : "Unassigned",
        createdAt: finding.createdAt,
        updatedAt: finding.updatedAt,
        thumbnailUrl: frame?.thumbnailUrl,
        commentCount: commentCountByFinding[finding.id] ?? 0,
      };
    });

  const apiImages =
    apiSamples?.results.flatMap((sample) => sample.cameras) ?? [];
  const apiImageById = new Map(apiImages.map((image) => [image.id, image]));
  const apiTasks: OverviewTask[] = apiCases.map((qaCase) => {
    const risk = Math.round(qaCase.riskScore);
    const sourceImage = qaCase.sourceImageId
      ? apiImageById.get(qaCase.sourceImageId)
      : undefined;
    return {
      id: qaCase.id,
      frameId: qaCase.sourceImageId ?? qaCase.frameFileName,
      frameNumber: qaCase.frameIndex,
      title: `${qaCase.className} · ${findingTypeLabels[qaCase.errorType]}`,
      type: qaCase.errorType,
      severity: qaCase.priority ?? riskToSeverity(risk),
      risk,
      stage: stageFromStatus(qaCase.status),
      status: qaCase.status,
      assigneeId: qaCase.assignedTo ?? undefined,
      ownerName: qaCase.assignedTo ?? "Unassigned",
      createdAt: qaCase.createdAt,
      updatedAt: qaCase.updatedAt,
      thumbnailUrl: qaCase.evidence.imageUrl ?? sourceImage?.imageUrl,
      commentCount: 0,
    };
  });

  const tasks = apiDataSourceEnabled ? apiTasks : mockTasks;
  const openTasks = tasks.filter(taskIsOpen);
  const roleTasks = openTasks.filter((task) =>
    taskMatchesRole(task, role, state.activeUserId),
  );
  const priorityTasks = [...(roleTasks.length ? roleTasks : openTasks)]
    .sort(sortTasks)
    .slice(0, 6);
  const primaryTask = priorityTasks[0];
  const latestUpdate = tasks.reduce<string | undefined>(
    (latest, task) => {
      if (!latest || Date.parse(task.updatedAt) > Date.parse(latest))
        return task.updatedAt;
      return latest;
    },
    apiDataSourceEnabled ? undefined : state.lastUpdatedAt,
  );

  const funnel = [
    {
      key: "assigned",
      label: "Assigned",
      stages: ["assigned"] as TaskWorkflowStage[],
    },
    {
      key: "progress",
      label: "In progress",
      stages: ["in_progress"] as TaskWorkflowStage[],
    },
    {
      key: "submitted",
      label: "Submitted",
      stages: ["submitted"] as TaskWorkflowStage[],
    },
    {
      key: "review",
      label: "Review",
      stages: ["in_review", "resubmitted"] as TaskWorkflowStage[],
    },
    {
      key: "rework",
      label: "Rework",
      stages: ["changes_requested"] as TaskWorkflowStage[],
    },
    {
      key: "approved",
      label: "Approved",
      stages: ["approved"] as TaskWorkflowStage[],
    },
  ].map((item) => ({
    ...item,
    count: tasks.filter((task) => item.stages.includes(task.stage)).length,
  }));

  const heatCounts = severityOrder.map((severity) =>
    ageColumns.map(
      (column) =>
        openTasks.filter((task) => {
          const age = daysSince(task.createdAt, now);
          return (
            task.severity === severity && age >= column.min && age < column.max
          );
        }).length,
    ),
  );
  const maxHeatCount = Math.max(1, ...heatCounts.flat());

  const waitingReview = tasks.filter((task) =>
    ["submitted", "resubmitted"].includes(task.stage),
  ).length;
  const reworkCount = tasks.filter(
    (task) => task.stage === "changes_requested",
  ).length;
  const criticalOpen = openTasks.filter((task) =>
    ["critical", "high"].includes(task.severity),
  ).length;
  const unresolvedComments = apiDataSourceEnabled
    ? 0
    : state.feedbackComments.filter(
        (comment) => !comment.resolved && comment.blocking,
      ).length;
  const disagreementCount = tasks.filter(
    (task) => task.type === "wrong_class" || task.status === "rejected",
  ).length;
  const enabledChecks = apiDataSourceEnabled
    ? 6
    : state.rules.filter((rule) => rule.enabled).length +
      state.models.filter((model) => model.enabled).length;

  const roleFacts: Record<Role, RoleFact[]> = {
    reviewer: [
      {
        label: "Waiting review",
        value: waitingReview,
        tone: waitingReview ? "warning" : "success",
      },
      {
        label: "Rework",
        value: reworkCount,
        tone: reworkCount ? "warning" : "neutral",
      },
      {
        label: "High risk open",
        value: criticalOpen,
        tone: criticalOpen ? "danger" : "success",
      },
      { label: "My active queue", value: roleTasks.length },
    ],
    annotator: [
      {
        label: "Assigned now",
        value: roleTasks.filter((task) => task.stage === "assigned").length,
      },
      {
        label: "Changes requested",
        value: roleTasks.filter((task) => task.stage === "changes_requested")
          .length,
        tone: "warning",
      },
      {
        label: "Blocking comments",
        value: unresolvedComments,
        tone: unresolvedComments ? "danger" : "success",
      },
      {
        label: "Batch submitted",
        value: selectedBatch
          ? `${selectedBatch.submittedCount}/${selectedBatch.frameCount}`
          : "Not tracked",
      },
    ],
    admin: [
      {
        label: "Disagreement signals",
        value: disagreementCount,
        tone: disagreementCount ? "warning" : "success",
      },
      {
        label: "High risk signals",
        value: criticalOpen,
        tone: criticalOpen ? "danger" : "success",
      },
      {
        label: "Evaluation",
        value: apiDataSourceEnabled
          ? realQaRunStatus
          : state.qaRun.status === "running"
            ? `${state.qaRun.progress}%`
            : state.qaRun.status,
      },
      { label: "Active checks", value: enabledChecks },
    ],
  };

  const approved =
    selectedBatch?.approvedCount ??
    tasks.filter((task) => task.stage === "approved").length;
  const submitted =
    selectedBatch?.submittedCount ??
    tasks.filter((task) =>
      [
        "submitted",
        "in_review",
        "changes_requested",
        "resubmitted",
        "approved",
      ].includes(task.stage),
    ).length;
  const assigned =
    selectedBatch?.assignedCount ??
    tasks.filter((task) => task.stage !== "unassigned").length;
  const healthTotal = Math.max(selectedBatch?.frameCount ?? tasks.length, 1);
  const healthSegments = [
    { label: "Approved", value: approved, className: "is-approved" },
    {
      label: "Review",
      value: Math.max(0, submitted - approved),
      className: "is-review",
    },
    {
      label: "Labeling",
      value: Math.max(0, assigned - submitted),
      className: "is-labeling",
    },
    {
      label: "Unassigned",
      value: Math.max(0, healthTotal - assigned),
      className: "is-unassigned",
    },
  ];
  const approvalPercent = Math.round((approved / healthTotal) * 100);
  const apiLoading =
    apiDataSourceEnabled &&
    (apiCasesQuery.isPending || apiSamplesQuery.isPending);
  const apiError =
    apiDataSourceEnabled && (apiCasesQuery.isError || apiSamplesQuery.isError);
  const displayDatasetName = apiDataSourceEnabled
    ? apiDataset === "nuscenes"
      ? "nuScenes official"
      : "KITTI official"
    : (selectedDataset?.name ?? "No dataset");
  const displayVersion = apiDataSourceEnabled
    ? apiSplit
    : (selectedDataset?.version ?? "—");
  const batchName = apiDataSourceEnabled
    ? `Serving ${apiSamples?.split ?? apiSplit}`
    : (selectedBatch?.name ?? "No active batch");
  const customerName = apiDataSourceEnabled
    ? "Official dataset"
    : (selectedBatch?.customerName ?? "Unassigned");
  const systemState = apiError
    ? "Data connection needs attention"
    : apiLoading
      ? "Syncing workspace"
      : criticalOpen
        ? "Review required"
        : "Workspace healthy";

  const openTask = (task?: OverviewTask) => {
    if (task && onOpenFinding && !apiDataSourceEnabled) {
      onOpenFinding(task.id);
      return;
    }
    onOpenQueue();
  };

  return (
    <div className="page-container view-page ov2" data-role={role}>
      <header className="ov2-header">
        <div className="ov2-heading-row">
          <div>
            <h1>{roleCopy[role].title}</h1>
            <p>
              {roleCopy[role].label} · {activeUser?.name ?? "Workspace user"}
            </p>
          </div>
          <Button
            className="ov2-primary-action"
            variant="primary"
            onClick={() => openTask(primaryTask)}
          >
            {role === "admin" ? <ScanSearch size={16} /> : <Play size={16} />}
            {roleCopy[role].action}
            <ArrowRight size={16} />
          </Button>
        </div>

        <div className="ov2-context-bar" aria-label="Active workspace context">
          <div className="ov2-context-main">
            <span className="ov2-context-icon">
              <Database size={17} />
            </span>
            <span>
              <small>Dataset</small>
              <strong>{displayDatasetName}</strong>
            </span>
          </div>
          <div>
            <small>Version / split</small>
            <strong>{displayVersion}</strong>
          </div>
          <div>
            <small>Active batch</small>
            <strong>{batchName}</strong>
            <span>{customerName}</span>
          </div>
          <div>
            <small>Freshness</small>
            <strong>
              {latestUpdate
                ? `${formatAge(latestUpdate, now)} ago`
                : "Not tracked"}
            </strong>
            <span>
              {apiLoading ? "Sync in progress" : "Latest workspace event"}
            </span>
          </div>
          <div
            className={`ov2-context-health ${apiError ? "is-danger" : criticalOpen ? "is-warning" : "is-success"}`}
          >
            {apiError ? (
              <AlertTriangle size={16} />
            ) : criticalOpen ? (
              <Activity size={16} />
            ) : (
              <ShieldCheck size={16} />
            )}
            <span>
              <small>Health</small>
              <strong>{systemState}</strong>
            </span>
          </div>
        </div>

        <dl
          className="ov2-role-facts"
          aria-label={`${roleCopy[role].label} attention summary`}
        >
          {roleFacts[role].map((fact) => (
            <div
              key={fact.label}
              className={fact.tone ? `is-${fact.tone}` : undefined}
            >
              <dt>{fact.label}</dt>
              <dd>{fact.value}</dd>
            </div>
          ))}
        </dl>
      </header>

      <div className="ov2-mobile-fallback" role="note">
        <Monitor size={18} />
        <span>
          <strong>Review tools are optimized for desktop.</strong> Monitoring
          and task handoff remain available here.
        </span>
      </div>

      <main className="ov2-cockpit">
        <section
          className="ov2-panel ov2-funnel-panel"
          aria-labelledby="ov2-funnel-title"
        >
          <div className="ov2-section-heading">
            <div>
              <h2 id="ov2-funnel-title">Workflow</h2>
              <p>{tasks.length} tasks across the active dataset</p>
            </div>
            <button
              type="button"
              className="ov2-text-action"
              onClick={onOpenQueue}
            >
              Open queue <ChevronRight size={15} />
            </button>
          </div>
          <div
            className="ov2-funnel"
            role="list"
            aria-label="Task workflow stages"
          >
            {funnel.map((stage, index) => (
              <button
                key={stage.key}
                type="button"
                className={`ov2-funnel-stage ${stage.key === "rework" && stage.count ? "has-attention" : ""}`}
                onClick={onOpenQueue}
                role="listitem"
                aria-label={`${stage.label}: ${stage.count} tasks. Open queue.`}
              >
                <span className="ov2-stage-marker">
                  {stage.key === "approved" ? (
                    <CheckCircle2 size={15} />
                  ) : (
                    <CircleDot size={15} />
                  )}
                </span>
                <span>
                  <small>{stage.label}</small>
                  <strong>{stage.count}</strong>
                </span>
                {index < funnel.length - 1 ? (
                  <ChevronRight
                    className="ov2-stage-arrow"
                    size={15}
                    aria-hidden="true"
                  />
                ) : null}
              </button>
            ))}
          </div>
        </section>

        <div className="ov2-analysis-grid">
          <section
            className="ov2-panel ov2-attention-panel"
            aria-labelledby="ov2-attention-title"
          >
            <div className="ov2-section-heading">
              <div>
                <h2 id="ov2-attention-title">Attention map</h2>
                <p>Open risk by queue age</p>
              </div>
              <span className="ov2-panel-total">
                <AlertTriangle size={15} /> {openTasks.length} open
              </span>
            </div>
            <div
              className="ov2-heatmap"
              role="table"
              aria-label="Open task severity by age"
            >
              <div className="ov2-heatmap-corner" role="columnheader">
                Severity
              </div>
              {ageColumns.map((column) => (
                <div
                  key={column.label}
                  className="ov2-heatmap-head"
                  role="columnheader"
                >
                  {column.label}
                </div>
              ))}
              {severityOrder.map((severity, rowIndex) => (
                <div className="ov2-heatmap-row" role="row" key={severity}>
                  <div
                    className={`ov2-severity-label is-${severity}`}
                    role="rowheader"
                  >
                    <span />
                    {severityLabels[severity]}
                  </div>
                  {ageColumns.map((column, columnIndex) => {
                    const count = heatCounts[rowIndex][columnIndex];
                    const heatLevel = count
                      ? Math.max(1, Math.ceil((count / maxHeatCount) * 4))
                      : 0;
                    return (
                      <button
                        type="button"
                        key={column.label}
                        className="ov2-heat-cell"
                        style={{ "--heat-level": heatLevel } as CSSProperties}
                        onClick={onOpenQueue}
                        role="cell"
                        aria-label={`${count} ${severity} tasks aged ${column.label}. Open queue.`}
                      >
                        <span>{count}</span>
                      </button>
                    );
                  })}
                </div>
              ))}
            </div>
            <div className="ov2-heat-legend" aria-hidden="true">
              <span>Lower</span>
              <i />
              <i />
              <i />
              <i />
              <span>Higher</span>
            </div>
          </section>

          <section
            className="ov2-panel ov2-health-panel"
            aria-labelledby="ov2-health-title"
          >
            <div className="ov2-section-heading">
              <div>
                <h2 id="ov2-health-title">Dataset health</h2>
                <p>
                  {selectedBatch
                    ? selectedBatch.customerName
                    : displayDatasetName}
                </p>
              </div>
              <strong className="ov2-health-score">
                {approvalPercent}% <small>approved</small>
              </strong>
            </div>
            <div
              className="ov2-health-bar"
              aria-label={`${approvalPercent}% of frames approved`}
              role="progressbar"
              aria-valuenow={approvalPercent}
              aria-valuemin={0}
              aria-valuemax={100}
            >
              {healthSegments.map((segment) => (
                <span
                  key={segment.label}
                  className={segment.className}
                  style={{ width: `${(segment.value / healthTotal) * 100}%` }}
                  title={`${segment.label}: ${segment.value}`}
                />
              ))}
            </div>
            <div className="ov2-health-legend">
              {healthSegments.map((segment) => (
                <div key={segment.label}>
                  <span className={segment.className} />
                  <small>{segment.label}</small>
                  <strong>{segment.value}</strong>
                </div>
              ))}
            </div>
            <div className="ov2-health-signals">
              <div>
                <MessageSquareWarning size={16} />
                <span>
                  <small>Blocking feedback</small>
                  <strong>{unresolvedComments || "None"}</strong>
                </span>
              </div>
              <div>
                <RefreshCw size={16} />
                <span>
                  <small>Evaluation run</small>
                  <strong>
                    {apiDataSourceEnabled
                      ? realQaRunStatus === "running"
                        ? `${realQaRunProgress}% complete`
                        : realQaRunStatus
                      : state.qaRun.status === "running"
                        ? `${state.qaRun.progress}% complete`
                        : state.qaRun.status}
                  </strong>
                </span>
              </div>
              <div>
                <Layers3 size={16} />
                <span>
                  <small>Coverage</small>
                  <strong>
                    {assigned}/{healthTotal} assigned
                  </strong>
                </span>
              </div>
            </div>
          </section>
        </div>

        {role === "admin" ? (
          <section
            className="ov2-agent-strip"
            aria-label="Agent evaluation signals"
          >
            <div>
              <GitBranch size={17} />
              <span>
                <small>Model</small>
                <strong>
                  {apiDataSourceEnabled
                    ? realQaRunModelVersion
                    : state.qaRun.modelVersion}
                </strong>
              </span>
            </div>
            <div>
              <ShieldCheck size={17} />
              <span>
                <small>Rule set</small>
                <strong>
                  {apiDataSourceEnabled
                    ? realQaRunRuleVersion
                    : state.qaRun.ruleVersion}
                </strong>
              </span>
            </div>
            <div>
              <Activity size={17} />
              <span>
                <small>Reviewer disagreement</small>
                <strong>{disagreementCount} signals</strong>
              </span>
            </div>
            <button type="button" onClick={onOpenQueue}>
              Compare evidence <ChevronRight size={15} />
            </button>
          </section>
        ) : null}

        <section
          className="ov2-panel ov2-priority-panel"
          aria-labelledby="ov2-priority-title"
        >
          <div className="ov2-section-heading">
            <div>
              <h2 id="ov2-priority-title">Priority tasks</h2>
              <p>
                {priorityTasks.length
                  ? `Ordered for ${roleCopy[role].label.toLowerCase()} action`
                  : "No actionable task in this dataset"}
              </p>
            </div>
            <span className="ov2-panel-total">
              <UserRoundCheck size={15} /> {roleTasks.length} in role queue
            </span>
          </div>

          {priorityTasks.length ? (
            <div className="ov2-task-strip">
              {priorityTasks.map((task) => (
                <button
                  key={task.id}
                  type="button"
                  className="ov2-task"
                  onClick={() => openTask(task)}
                >
                  <span className="ov2-task-image">
                    {task.thumbnailUrl ? (
                      <img
                        src={task.thumbnailUrl}
                        alt={`Frame ${task.frameNumber ?? task.frameId}`}
                      />
                    ) : (
                      <Database size={20} aria-hidden="true" />
                    )}
                    <span>{task.frameNumber ?? task.frameId}</span>
                  </span>
                  <span className="ov2-task-body">
                    <span className="ov2-task-topline">
                      <span className={`ov2-severity-chip is-${task.severity}`}>
                        {severityLabels[task.severity]}
                      </span>
                      <span className="ov2-risk">Risk {task.risk}</span>
                    </span>
                    <strong>{task.title}</strong>
                    <span className="ov2-task-meta">
                      {findingTypeLabels[task.type]} · {stageLabels[task.stage]}
                    </span>
                    <span className="ov2-task-owner">{task.ownerName}</span>
                  </span>
                  <span className="ov2-task-footer">
                    <span>
                      <Clock3 size={14} /> {formatAge(task.createdAt, now)}
                    </span>
                    {task.commentCount ? (
                      <span>
                        <MessageSquareWarning size={14} /> {task.commentCount}
                      </span>
                    ) : null}
                    <strong>
                      {nextActionFor(role, task.stage)}{" "}
                      <ChevronRight size={14} />
                    </strong>
                  </span>
                </button>
              ))}
            </div>
          ) : (
            <div className="ov2-empty-state">
              <CheckCircle2 size={20} />
              <span>
                <strong>Queue is clear.</strong> New assignments and review
                feedback will appear here.
              </span>
              <Button variant="secondary" onClick={onOpenQueue}>
                Open all tasks
              </Button>
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
