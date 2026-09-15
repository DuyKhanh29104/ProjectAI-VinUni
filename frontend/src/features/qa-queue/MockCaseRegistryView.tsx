import {
  AlertTriangle,
  ArrowUpDown,
  Check,
  CheckCircle2,
  ChevronRight,
  CircleDot,
  Clock3,
  ExternalLink,
  Eye,
  Inbox,
  ListFilter,
  MessageSquareText,
  PanelRightClose,
  PencilLine,
  RotateCcw,
  Search,
  Send,
  ShieldCheck,
  UserRound,
  UserRoundPlus,
  X,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import type {
  FeedbackComment,
  Finding,
  Severity,
  TaskWorkflowStage,
} from "../../domain/types";
import { useMockData } from "../../state/MockDataProvider";
import { findingTypeLabels } from "./queuePresentation";

type SavedViewId =
  | "all"
  | "my_work"
  | "unassigned"
  | "awaiting_review"
  | "changes_requested"
  | "escalated"
  | "assigned"
  | "submitted";

type ReasonCategory = FeedbackComment["reasonCategory"];

const workflowStages: TaskWorkflowStage[] = [
  "unassigned",
  "assigned",
  "in_progress",
  "submitted",
  "in_review",
  "changes_requested",
  "resubmitted",
  "approved",
];

const severities: Severity[] = ["critical", "high", "medium", "low"];

const workflowLabels: Record<TaskWorkflowStage, string> = {
  unassigned: "Unassigned",
  assigned: "Assigned",
  in_progress: "In progress",
  submitted: "Submitted",
  in_review: "In review",
  changes_requested: "Changes requested",
  resubmitted: "Resubmitted",
  approved: "Approved",
};

const severityLabels: Record<Severity, string> = {
  critical: "Critical",
  high: "High",
  medium: "Medium",
  low: "Low",
};

const reasonLabels: Record<ReasonCategory, string> = {
  geometry: "Bounding box geometry",
  class: "Object class",
  missing_label: "Missing label",
  tracking: "Track continuity",
  other: "Other",
};

const reviewerViews: Array<{ id: SavedViewId; label: string }> = [
  { id: "all", label: "All cases" },
  { id: "my_work", label: "My work" },
  { id: "unassigned", label: "Unassigned" },
  { id: "awaiting_review", label: "Awaiting review" },
  { id: "changes_requested", label: "Changes requested" },
  { id: "escalated", label: "Escalated" },
];

const annotatorViews: Array<{ id: SavedViewId; label: string }> = [
  { id: "assigned", label: "Assigned to me" },
  { id: "changes_requested", label: "Rework" },
  { id: "submitted", label: "Submitted" },
  { id: "all", label: "All assigned" },
];

function matchesSavedView(
  finding: Finding,
  view: SavedViewId,
  activeUserId: string,
): boolean {
  if (view === "all") return true;
  if (view === "my_work") return finding.assigneeId === activeUserId;
  if (view === "unassigned") {
    return !finding.assigneeId || finding.workflowStage === "unassigned";
  }
  if (view === "awaiting_review") {
    return ["submitted", "resubmitted", "in_review"].includes(
      finding.workflowStage,
    );
  }
  if (view === "changes_requested")
    return finding.workflowStage === "changes_requested";
  if (view === "escalated") return finding.outcome === "escalated";
  if (view === "assigned") {
    return (
      finding.assigneeId === activeUserId &&
      finding.workflowStage !== "approved"
    );
  }
  return ["submitted", "resubmitted", "approved"].includes(
    finding.workflowStage,
  );
}

function formatAge(timestamp: string): string {
  const elapsedMs = Math.max(0, Date.now() - new Date(timestamp).getTime());
  const hours = Math.floor(elapsedMs / 3_600_000);
  if (hours < 1) return "< 1h";
  if (hours < 24) return `${hours}h`;
  return `${Math.floor(hours / 24)}d`;
}

function formatDateTime(timestamp: string): string {
  return new Intl.DateTimeFormat("en", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(timestamp));
}

function StageBadge({ stage }: { stage: TaskWorkflowStage }) {
  return (
    <span className={`case-registry-stage stage-${stage}`}>
      <CircleDot aria-hidden="true" size={12} />
      {workflowLabels[stage]}
    </span>
  );
}

export function MockCaseRegistryView({
  onOpenFinding,
  onOpenEditor,
}: {
  onOpenFinding?: (findingId: string) => void;
  onOpenEditor?: (split?: string, imageId?: string) => void;
}) {
  const { state, actions } = useMockData();
  const searchRef = useRef<HTMLInputElement>(null);
  const isAnnotator = state.activeRole === "annotator";
  const isReviewer = state.activeRole === "reviewer";
  const canAssign =
    state.activeRole === "reviewer" || state.activeRole === "admin";
  const savedViews = isAnnotator ? annotatorViews : reviewerViews;

  const [savedView, setSavedView] = useState<SavedViewId>(
    isAnnotator ? "assigned" : "all",
  );
  const [query, setQuery] = useState("");
  const [stageFilter, setStageFilter] = useState<TaskWorkflowStage | "all">(
    "all",
  );
  const [severityFilter, setSeverityFilter] = useState<Severity | "all">("all");
  const [assigneeFilter, setAssigneeFilter] = useState("all");
  const [batchFilter, setBatchFilter] = useState("all");
  const [selectedFindingId, setSelectedFindingId] = useState("");
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [bulkAssigneeId, setBulkAssigneeId] = useState("user-annotator");
  const [requestChangesOpen, setRequestChangesOpen] = useState(false);
  const [reasonCategory, setReasonCategory] =
    useState<ReasonCategory>("geometry");
  const [requestAssigneeId, setRequestAssigneeId] = useState("user-annotator");
  const [requestComment, setRequestComment] = useState("");
  const [formError, setFormError] = useState("");
  const [announcement, setAnnouncement] = useState("");

  const activeUser = state.users.find((user) => user.id === state.activeUserId);
  const userById = useMemo(
    () => new Map(state.users.map((user) => [user.id, user])),
    [state.users],
  );
  const batchById = useMemo(
    () => new Map(state.batches.map((batch) => [batch.id, batch])),
    [state.batches],
  );
  const frameById = useMemo(
    () => new Map(state.frames.map((frame) => [frame.id, frame])),
    [state.frames],
  );
  const sceneById = useMemo(
    () => new Map(state.scenes.map((scene) => [scene.id, scene])),
    [state.scenes],
  );
  const annotationById = useMemo(
    () =>
      new Map(
        state.annotations.map((annotation) => [annotation.id, annotation]),
      ),
    [state.annotations],
  );

  const roleScopedFindings = useMemo(
    () =>
      isAnnotator
        ? state.findings.filter(
            (finding) => finding.assigneeId === state.activeUserId,
          )
        : state.findings,
    [isAnnotator, state.activeUserId, state.findings],
  );

  const savedViewCounts = useMemo(
    () =>
      new Map(
        savedViews.map((view) => [
          view.id,
          roleScopedFindings.filter((finding) =>
            matchesSavedView(finding, view.id, state.activeUserId),
          ).length,
        ]),
      ),
    [roleScopedFindings, savedViews, state.activeUserId],
  );

  const visibleFindings = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase();
    return roleScopedFindings
      .filter((finding) =>
        matchesSavedView(finding, savedView, state.activeUserId),
      )
      .filter(
        (finding) =>
          stageFilter === "all" || finding.workflowStage === stageFilter,
      )
      .filter(
        (finding) =>
          severityFilter === "all" || finding.severity === severityFilter,
      )
      .filter(
        (finding) =>
          assigneeFilter === "all" || finding.assigneeId === assigneeFilter,
      )
      .filter(
        (finding) => batchFilter === "all" || finding.batchId === batchFilter,
      )
      .filter((finding) => {
        if (!normalizedQuery) return true;
        const batch = batchById.get(finding.batchId);
        const scene = sceneById.get(finding.sceneId);
        const annotation = finding.annotationId
          ? annotationById.get(finding.annotationId)
          : undefined;
        return [
          finding.id,
          finding.title,
          finding.type,
          finding.trackId,
          batch?.name,
          batch?.customerName,
          scene?.name,
          annotation?.label,
        ]
          .filter(Boolean)
          .join(" ")
          .toLocaleLowerCase()
          .includes(normalizedQuery);
      })
      .sort((first, second) => {
        if (first.priority !== second.priority)
          return first.priority - second.priority;
        return second.riskScore - first.riskScore;
      });
  }, [
    annotationById,
    assigneeFilter,
    batchById,
    batchFilter,
    query,
    roleScopedFindings,
    savedView,
    sceneById,
    severityFilter,
    stageFilter,
    state.activeUserId,
  ]);

  const selectedFinding = state.findings.find(
    (finding) => finding.id === selectedFindingId,
  );
  const selectedFrame = selectedFinding
    ? frameById.get(selectedFinding.frameId)
    : undefined;
  const selectedScene = selectedFinding
    ? sceneById.get(selectedFinding.sceneId)
    : undefined;
  const selectedBatch = selectedFinding
    ? batchById.get(selectedFinding.batchId)
    : undefined;
  const selectedAnnotation = selectedFinding?.annotationId
    ? annotationById.get(selectedFinding.annotationId)
    : undefined;
  const selectedEvidence = selectedFinding
    ? state.evidences.filter((evidence) =>
        selectedFinding.evidenceIds.includes(evidence.id),
      )
    : [];
  const selectedComments = selectedFinding
    ? state.feedbackComments
        .filter((comment) => comment.findingId === selectedFinding.id)
        .sort((first, second) =>
          second.createdAt.localeCompare(first.createdAt),
        )
    : [];

  const filterCount = [
    stageFilter !== "all",
    severityFilter !== "all",
    assigneeFilter !== "all",
    batchFilter !== "all",
    Boolean(query.trim()),
  ].filter(Boolean).length;

  const allVisibleSelected =
    visibleFindings.length > 0 &&
    visibleFindings.every((finding) => selectedIds.includes(finding.id));

  const nextFinding = visibleFindings.find(
    (finding) => finding.workflowStage !== "approved",
  );

  useEffect(() => {
    setSavedView(isAnnotator ? "assigned" : "all");
    setSelectedIds([]);
    setRequestChangesOpen(false);
  }, [isAnnotator]);

  useEffect(() => {
    setSelectedIds((current) =>
      current.filter((id) =>
        visibleFindings.some((finding) => finding.id === id),
      ),
    );
    if (
      selectedFindingId &&
      !visibleFindings.some((finding) => finding.id === selectedFindingId)
    ) {
      setSelectedFindingId("");
    }
  }, [selectedFindingId, visibleFindings]);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      const isTyping = target?.matches(
        "input, textarea, select, [contenteditable='true']",
      );
      if (event.key === "/" && !isTyping) {
        event.preventDefault();
        searchRef.current?.focus();
      }
      if (event.key === "Escape" && requestChangesOpen) {
        setRequestChangesOpen(false);
        setFormError("");
      }
      if (
        (event.key === "j" || event.key === "k") &&
        !isTyping &&
        visibleFindings.length
      ) {
        event.preventDefault();
        const currentIndex = visibleFindings.findIndex(
          (finding) => finding.id === selectedFindingId,
        );
        const direction = event.key === "j" ? 1 : -1;
        const nextIndex = Math.min(
          visibleFindings.length - 1,
          Math.max(0, currentIndex < 0 ? 0 : currentIndex + direction),
        );
        setSelectedFindingId(visibleFindings[nextIndex].id);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [requestChangesOpen, selectedFindingId, visibleFindings]);

  const clearFilters = () => {
    setQuery("");
    setStageFilter("all");
    setSeverityFilter("all");
    setAssigneeFilter("all");
    setBatchFilter("all");
  };

  const selectFinding = (findingId: string) => {
    setSelectedFindingId(findingId);
    setRequestChangesOpen(false);
    setFormError("");
  };

  const toggleSelected = (findingId: string) => {
    if (!canAssign) return;
    setSelectedIds((current) =>
      current.includes(findingId)
        ? current.filter((id) => id !== findingId)
        : [...current, findingId],
    );
  };

  const toggleAllVisible = () => {
    if (!canAssign) return;
    setSelectedIds(
      allVisibleSelected ? [] : visibleFindings.map((finding) => finding.id),
    );
  };

  const applyBulkAssignment = () => {
    selectedIds.forEach((findingId) =>
      actions.assignFinding(findingId, bulkAssigneeId),
    );
    setAnnouncement(`${selectedIds.length} cases assigned.`);
    setSelectedIds([]);
  };

  const applyBulkReview = () => {
    selectedIds.forEach((findingId) =>
      actions.setFindingStatus(
        findingId,
        "in_review",
        "start_review",
        "Started from QA Cases bulk action",
      ),
    );
    setAnnouncement(`${selectedIds.length} cases moved to review.`);
    setSelectedIds([]);
  };

  const openNextCase = () => {
    if (!nextFinding) return;
    selectFinding(nextFinding.id);
    if (isReviewer) {
      actions.setFindingStatus(
        nextFinding.id,
        "in_review",
        "start_review",
        "Opened from QA Cases registry",
      );
      onOpenFinding?.(nextFinding.id);
      return;
    }
    if (isAnnotator) {
      onOpenEditor?.();
      return;
    }
    onOpenFinding?.(nextFinding.id);
  };

  const handleRequestChanges = () => {
    if (!selectedFinding) return;
    if (!requestComment.trim()) {
      setFormError("Add a specific instruction for the annotator.");
      return;
    }
    actions.requestChanges(
      selectedFinding.id,
      requestAssigneeId,
      requestComment.trim(),
      reasonCategory,
    );
    setAnnouncement(`Changes requested for ${selectedFinding.id}.`);
    setRequestComment("");
    setFormError("");
    setRequestChangesOpen(false);
  };

  const runReviewAction = (message: string, action: () => void) => {
    action();
    setAnnouncement(message);
  };

  return (
    <div className="case-registry-v2">
      <header className="case-registry-header">
        <div>
          <h1>QA Cases</h1>
          <p>
            {isAnnotator
              ? "Your assigned frames, reviewer feedback and submitted revisions."
              : "Case ownership, workflow state and audit-ready review decisions."}
          </p>
        </div>
        {nextFinding ? (
          <button
            className="case-registry-primary"
            type="button"
            onClick={openNextCase}
          >
            {isAnnotator ? (
              <PencilLine aria-hidden="true" size={16} />
            ) : (
              <Eye aria-hidden="true" size={16} />
            )}
            {isAnnotator
              ? "Continue task"
              : isReviewer
                ? "Review next"
                : "Inspect next"}
          </button>
        ) : null}
      </header>

      <nav className="case-registry-saved-views" aria-label="Saved case views">
        {savedViews.map((view) => (
          <button
            className={savedView === view.id ? "is-active" : ""}
            type="button"
            key={view.id}
            aria-current={savedView === view.id ? "page" : undefined}
            onClick={() => {
              setSavedView(view.id);
              setSelectedIds([]);
            }}
          >
            <span>{view.label}</span>
            <strong>{savedViewCounts.get(view.id) ?? 0}</strong>
          </button>
        ))}
      </nav>

      <section className="case-registry-filterbar" aria-label="Case filters">
        <label className="case-registry-search">
          <Search aria-hidden="true" size={16} />
          <span className="sr-only">Search cases</span>
          <input
            ref={searchRef}
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search case, frame, class or batch"
          />
          <kbd>/</kbd>
        </label>
        <label>
          <span className="sr-only">Workflow stage</span>
          <select
            value={stageFilter}
            onChange={(event) =>
              setStageFilter(event.target.value as TaskWorkflowStage | "all")
            }
          >
            <option value="all">All stages</option>
            {workflowStages.map((stage) => (
              <option value={stage} key={stage}>
                {workflowLabels[stage]}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span className="sr-only">Severity</span>
          <select
            value={severityFilter}
            onChange={(event) =>
              setSeverityFilter(event.target.value as Severity | "all")
            }
          >
            <option value="all">All severity</option>
            {severities.map((severity) => (
              <option value={severity} key={severity}>
                {severityLabels[severity]}
              </option>
            ))}
          </select>
        </label>
        {!isAnnotator ? (
          <label>
            <span className="sr-only">Assignee</span>
            <select
              value={assigneeFilter}
              onChange={(event) => setAssigneeFilter(event.target.value)}
            >
              <option value="all">All assignees</option>
              {state.users
                .filter((user) => user.role !== "admin")
                .map((user) => (
                  <option value={user.id} key={user.id}>
                    {user.name}
                  </option>
                ))}
            </select>
          </label>
        ) : null}
        <label>
          <span className="sr-only">Batch</span>
          <select
            value={batchFilter}
            onChange={(event) => setBatchFilter(event.target.value)}
          >
            <option value="all">All batches</option>
            {state.batches.map((batch) => (
              <option value={batch.id} key={batch.id}>
                {batch.name}
              </option>
            ))}
          </select>
        </label>
        <div className="case-registry-filter-summary">
          <ListFilter aria-hidden="true" size={14} />
          <span>{filterCount ? `${filterCount} active` : "No filters"}</span>
          {filterCount ? (
            <button
              type="button"
              onClick={clearFilters}
              aria-label="Clear all filters"
            >
              <RotateCcw aria-hidden="true" size={14} />
            </button>
          ) : null}
        </div>
      </section>

      <div
        className={`case-registry-workspace ${selectedFinding ? "has-inspector" : ""}`}
      >
        <main className="case-registry-table-panel">
          <div className="case-registry-table-meta">
            <span>
              <strong>{visibleFindings.length}</strong> cases
            </span>
            <span>
              <ArrowUpDown aria-hidden="true" size={13} /> Priority, then risk
            </span>
          </div>
          <div className="case-registry-table-scroll">
            <table
              className={`case-registry-table ${canAssign ? "can-select" : "no-select"}`}
            >
              <thead>
                <tr>
                  {canAssign ? (
                    <th className="case-registry-check-cell">
                      <input
                        type="checkbox"
                        checked={allVisibleSelected}
                        onChange={toggleAllVisible}
                        aria-label="Select all visible cases"
                      />
                    </th>
                  ) : null}
                  <th className="case-registry-col-frame">Frame</th>
                  <th className="case-registry-col-case">Case</th>
                  <th className="case-registry-col-issue">Issue</th>
                  <th className="case-registry-col-risk">Risk</th>
                  <th className="case-registry-col-workflow">Workflow</th>
                  <th className="case-registry-col-owner">Owner</th>
                  <th className="case-registry-col-activity">Activity</th>
                  <th className="case-registry-col-open">
                    <span className="sr-only">Open inspector</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {visibleFindings.map((finding) => {
                  const frame = frameById.get(finding.frameId);
                  const scene = sceneById.get(finding.sceneId);
                  const annotation = finding.annotationId
                    ? annotationById.get(finding.annotationId)
                    : undefined;
                  const assignee = finding.assigneeId
                    ? userById.get(finding.assigneeId)
                    : undefined;
                  const unresolvedComments = state.feedbackComments.filter(
                    (comment) =>
                      comment.findingId === finding.id && !comment.resolved,
                  ).length;
                  return (
                    <tr
                      key={finding.id}
                      className={
                        selectedFindingId === finding.id ? "is-active" : ""
                      }
                      onClick={() => selectFinding(finding.id)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          selectFinding(finding.id);
                        }
                      }}
                      tabIndex={0}
                      aria-selected={selectedFindingId === finding.id}
                    >
                      {canAssign ? (
                        <td
                          className="case-registry-check-cell"
                          data-label="Select"
                        >
                          <input
                            type="checkbox"
                            checked={selectedIds.includes(finding.id)}
                            onClick={(event) => event.stopPropagation()}
                            onChange={() => toggleSelected(finding.id)}
                            aria-label={`Select ${finding.id}`}
                          />
                        </td>
                      ) : null}
                      <td data-label="Frame">
                        <span className="case-registry-frame-cell">
                          {frame?.thumbnailUrl ? (
                            <img src={frame.thumbnailUrl} alt="" />
                          ) : (
                            <span className="case-registry-image-fallback">
                              <Inbox size={15} />
                            </span>
                          )}
                          <span>
                            <strong>
                              Frame {frame?.frameNumber ?? "Unknown"}
                            </strong>
                            <small>{scene?.name ?? finding.sceneId}</small>
                          </span>
                        </span>
                      </td>
                      <td data-label="Case">
                        <span className="case-registry-case-cell">
                          <strong>
                            {annotation?.label ?? "Missing label"}
                          </strong>
                          <small>{finding.id}</small>
                        </span>
                      </td>
                      <td data-label="Issue">
                        <span className="case-registry-issue-cell">
                          <strong>{findingTypeLabels[finding.type]}</strong>
                          <small>{finding.trackId ?? "Frame level"}</small>
                        </span>
                      </td>
                      <td data-label="Risk">
                        <span
                          className={`case-registry-risk risk-${finding.severity}`}
                        >
                          <strong>{Math.round(finding.riskScore * 100)}</strong>
                          <small>{severityLabels[finding.severity]}</small>
                        </span>
                      </td>
                      <td data-label="Workflow">
                        <StageBadge stage={finding.workflowStage} />
                      </td>
                      <td data-label="Owner">
                        <span className="case-registry-owner">
                          <span>{assignee?.avatarInitials ?? "--"}</span>
                          <small>{assignee?.name ?? "Unassigned"}</small>
                        </span>
                      </td>
                      <td data-label="Activity">
                        <span className="case-registry-activity">
                          <span>
                            <Clock3 aria-hidden="true" size={12} />
                            {formatAge(finding.updatedAt)}
                          </span>
                          {unresolvedComments ? (
                            <span className="has-comments">
                              <MessageSquareText aria-hidden="true" size={12} />
                              {unresolvedComments}
                            </span>
                          ) : null}
                        </span>
                      </td>
                      <td className="case-registry-open-cell">
                        <ChevronRight aria-hidden="true" size={16} />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {!visibleFindings.length ? (
            <div className="case-registry-empty">
              <Inbox aria-hidden="true" size={28} />
              <strong>No cases in this view</strong>
              <span>Try another saved view or clear the active filters.</span>
              {filterCount ? (
                <button type="button" onClick={clearFilters}>
                  Clear filters
                </button>
              ) : null}
            </div>
          ) : null}
        </main>

        {selectedFinding ? (
          <aside
            className="case-registry-inspector"
            aria-labelledby="case-inspector-title"
          >
            <div className="case-registry-inspector-head">
              <div>
                <span>{selectedFinding.id}</span>
                <h2 id="case-inspector-title">{selectedFinding.title}</h2>
              </div>
              <button
                type="button"
                onClick={() => setSelectedFindingId("")}
                aria-label="Close case inspector"
                title="Close inspector"
              >
                <PanelRightClose aria-hidden="true" size={17} />
              </button>
            </div>

            <div className="case-registry-preview">
              {selectedFrame?.thumbnailUrl ? (
                <img
                  src={selectedFrame.thumbnailUrl}
                  alt={`Frame ${selectedFrame.frameNumber}`}
                />
              ) : (
                <div className="case-registry-preview-empty">
                  <Inbox size={22} />
                  <span>Preview unavailable</span>
                </div>
              )}
              <div>
                <StageBadge stage={selectedFinding.workflowStage} />
                <span
                  className={`case-registry-severity severity-${selectedFinding.severity}`}
                >
                  <AlertTriangle aria-hidden="true" size={12} />
                  {severityLabels[selectedFinding.severity]}
                </span>
              </div>
            </div>

            <dl className="case-registry-facts">
              <div>
                <dt>Batch</dt>
                <dd>{selectedBatch?.name ?? selectedFinding.batchId}</dd>
              </div>
              <div>
                <dt>Frame</dt>
                <dd>
                  {selectedScene?.name ?? selectedFinding.sceneId} /{" "}
                  {selectedFrame?.frameNumber ?? "Unknown"}
                </dd>
              </div>
              <div>
                <dt>Object</dt>
                <dd>{selectedAnnotation?.label ?? "Missing label"}</dd>
              </div>
              <div>
                <dt>Assignee</dt>
                <dd>
                  {selectedFinding.assigneeId
                    ? userById.get(selectedFinding.assigneeId)?.name
                    : "Unassigned"}
                </dd>
              </div>
              <div>
                <dt>Risk</dt>
                <dd>{Math.round(selectedFinding.riskScore * 100)} / 100</dd>
              </div>
              <div>
                <dt>Updated</dt>
                <dd>{formatDateTime(selectedFinding.updatedAt)}</dd>
              </div>
            </dl>

            <section className="case-registry-inspector-section">
              <div className="case-registry-section-title">
                <h3>Agent evidence</h3>
                <span>{selectedEvidence.length}</span>
              </div>
              <p className="case-registry-summary">{selectedFinding.summary}</p>
              <div className="case-registry-evidence-list">
                {selectedEvidence.map((evidence) => (
                  <div key={evidence.id}>
                    <span>{evidence.metric}</span>
                    <strong>{String(evidence.value)}</strong>
                  </div>
                ))}
              </div>
            </section>

            <section className="case-registry-inspector-section">
              <div className="case-registry-section-title">
                <h3>Feedback</h3>
                <span>
                  {
                    selectedComments.filter((comment) => !comment.resolved)
                      .length
                  }{" "}
                  open
                </span>
              </div>
              {selectedComments.length ? (
                <div className="case-registry-comment-list">
                  {selectedComments.map((comment) => {
                    const author = userById.get(comment.authorId);
                    return (
                      <article
                        key={comment.id}
                        className={comment.resolved ? "is-resolved" : ""}
                      >
                        <header>
                          <span>{author?.avatarInitials ?? "--"}</span>
                          <div>
                            <strong>{author?.name ?? "Unknown user"}</strong>
                            <small>
                              {reasonLabels[comment.reasonCategory]} /{" "}
                              {formatDateTime(comment.createdAt)}
                            </small>
                          </div>
                          {comment.blocking && !comment.resolved ? (
                            <em>Blocking</em>
                          ) : null}
                        </header>
                        <p>{comment.body}</p>
                        {isAnnotator && !comment.resolved ? (
                          <button
                            type="button"
                            onClick={() => actions.resolveFeedback(comment.id)}
                          >
                            <Check aria-hidden="true" size={13} /> Mark
                            addressed
                          </button>
                        ) : null}
                      </article>
                    );
                  })}
                </div>
              ) : (
                <p className="case-registry-no-feedback">
                  No feedback on this case.
                </p>
              )}
            </section>

            {isReviewer && requestChangesOpen ? (
              <section
                className="case-registry-request-form"
                aria-label="Request changes"
              >
                <div className="case-registry-section-title">
                  <h3>Request changes</h3>
                  <button
                    type="button"
                    onClick={() => setRequestChangesOpen(false)}
                    aria-label="Cancel request changes"
                  >
                    <X size={15} />
                  </button>
                </div>
                <div className="case-registry-form-row">
                  <label>
                    <span>Reason</span>
                    <select
                      value={reasonCategory}
                      onChange={(event) =>
                        setReasonCategory(event.target.value as ReasonCategory)
                      }
                    >
                      {Object.entries(reasonLabels).map(([value, label]) => (
                        <option key={value} value={value}>
                          {label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    <span>Assign to</span>
                    <select
                      value={requestAssigneeId}
                      onChange={(event) =>
                        setRequestAssigneeId(event.target.value)
                      }
                    >
                      {state.users
                        .filter((user) => user.role === "annotator")
                        .map((user) => (
                          <option key={user.id} value={user.id}>
                            {user.name}
                          </option>
                        ))}
                    </select>
                  </label>
                </div>
                <label>
                  <span>Instruction</span>
                  <textarea
                    value={requestComment}
                    onChange={(event) => {
                      setRequestComment(event.target.value);
                      if (formError) setFormError("");
                    }}
                    maxLength={500}
                    rows={3}
                    placeholder="Describe what must change and anchor it to this frame or object."
                    aria-invalid={Boolean(formError)}
                    aria-describedby={
                      formError ? "request-changes-error" : undefined
                    }
                  />
                </label>
                {formError ? (
                  <p id="request-changes-error" role="alert">
                    {formError}
                  </p>
                ) : null}
                <div className="case-registry-form-actions">
                  <span>{requestComment.length}/500</span>
                  <button
                    className="case-registry-primary"
                    type="button"
                    onClick={handleRequestChanges}
                  >
                    <Send aria-hidden="true" size={15} /> Send to annotator
                  </button>
                </div>
              </section>
            ) : null}

            <div className="case-registry-inspector-actions">
              <div>
                {onOpenFinding ? (
                  <button
                    type="button"
                    onClick={() => onOpenFinding(selectedFinding.id)}
                  >
                    <ExternalLink aria-hidden="true" size={15} /> Open review
                  </button>
                ) : null}
                {onOpenEditor ? (
                  <button type="button" onClick={() => onOpenEditor()}>
                    <PencilLine aria-hidden="true" size={15} /> Open editor
                  </button>
                ) : null}
              </div>

              {isReviewer ? (
                !requestChangesOpen ? (
                  <div className="case-registry-decision-actions">
                    {selectedFinding.workflowStage === "submitted" ||
                    selectedFinding.workflowStage === "resubmitted" ? (
                      <button
                        className="case-registry-primary"
                        type="button"
                        onClick={() =>
                          runReviewAction(
                            `${selectedFinding.id} is in review.`,
                            () =>
                              actions.setFindingStatus(
                                selectedFinding.id,
                                "in_review",
                                "start_review",
                                "Review started from case registry",
                              ),
                          )
                        }
                      >
                        <Eye aria-hidden="true" size={15} /> Start review
                      </button>
                    ) : selectedFinding.workflowStage !== "approved" ? (
                      <button
                        className="case-registry-primary"
                        type="button"
                        onClick={() =>
                          runReviewAction(
                            `${selectedFinding.id} approved.`,
                            () =>
                              actions.approveFinding(
                                selectedFinding.id,
                                "Approved from QA Cases registry",
                              ),
                          )
                        }
                      >
                        <CheckCircle2 aria-hidden="true" size={15} /> Approve
                      </button>
                    ) : null}
                    {selectedFinding.workflowStage !== "approved" ? (
                      <button
                        type="button"
                        onClick={() => setRequestChangesOpen(true)}
                      >
                        <MessageSquareText aria-hidden="true" size={15} />{" "}
                        Request changes
                      </button>
                    ) : null}
                    {selectedFinding.workflowStage !== "approved" ? (
                      <button
                        type="button"
                        onClick={() =>
                          runReviewAction(
                            `${selectedFinding.id} marked false positive.`,
                            () =>
                              actions.setFindingStatus(
                                selectedFinding.id,
                                "rejected",
                                "reject_finding",
                                "Agent finding rejected from case registry",
                              ),
                          )
                        }
                      >
                        <ShieldCheck aria-hidden="true" size={15} /> False
                        positive
                      </button>
                    ) : null}
                  </div>
                ) : null
              ) : isAnnotator ? (
                <div className="case-registry-decision-actions">
                  {selectedFinding.workflowStage === "changes_requested" ? (
                    <button
                      className="case-registry-primary"
                      type="button"
                      onClick={() =>
                        runReviewAction(
                          `${selectedFinding.id} resubmitted for review.`,
                          () =>
                            actions.resubmitFinding(
                              selectedFinding.id,
                              "Revision submitted from QA Cases registry",
                            ),
                        )
                      }
                    >
                      <Send aria-hidden="true" size={15} /> Submit revision
                    </button>
                  ) : null}
                </div>
              ) : (
                <p className="case-registry-readonly">
                  <ShieldCheck size={14} /> Admin inspection is read-only. Use
                  assignment controls to route work.
                </p>
              )}
            </div>
          </aside>
        ) : null}
      </div>

      {selectedIds.length ? (
        <div
          className="case-registry-bulkbar"
          role="region"
          aria-label="Bulk case actions"
        >
          <div>
            <CheckCircle2 aria-hidden="true" size={17} />
            <strong>{selectedIds.length} selected</strong>
            <button
              type="button"
              onClick={() => setSelectedIds([])}
              aria-label="Clear selection"
            >
              <X size={15} />
            </button>
          </div>
          <label>
            <UserRoundPlus aria-hidden="true" size={15} />
            <span className="sr-only">Assign selected cases to</span>
            <select
              value={bulkAssigneeId}
              onChange={(event) => setBulkAssigneeId(event.target.value)}
            >
              {state.users
                .filter((user) => user.role !== "admin")
                .map((user) => (
                  <option key={user.id} value={user.id}>
                    {user.name}
                  </option>
                ))}
            </select>
          </label>
          {isReviewer ? (
            <button type="button" onClick={applyBulkReview}>
              <Eye size={15} /> Start review
            </button>
          ) : null}
          <button
            className="case-registry-primary"
            type="button"
            onClick={applyBulkAssignment}
          >
            <UserRoundPlus aria-hidden="true" size={15} /> Assign cases
          </button>
        </div>
      ) : null}

      <div className="sr-only" role="status" aria-live="polite">
        {announcement}
      </div>
      <span className="case-registry-role-note">
        <UserRound aria-hidden="true" size={13} />{" "}
        {activeUser?.name ?? "Active user"} / {state.activeRole}
      </span>
    </div>
  );
}
