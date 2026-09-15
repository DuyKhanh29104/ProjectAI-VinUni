import { useEffect, useMemo, useState } from "react";
import {
  ArrowRight,
  Check,
  ChevronLeft,
  ChevronRight,
  CircleAlert,
  MessageSquareText,
  PencilRuler,
  Play,
  RotateCcw,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  UserRoundCheck,
  X,
} from "lucide-react";
import { Button } from "../../components/ui";
import type {
  FeedbackComment,
  Finding,
  TaskWorkflowStage,
} from "../../domain/types";
import { useMockData } from "../../state/MockDataProvider";
import { MockQueueComparisonViewer } from "./components/MockQueueComparisonViewer";
import { findingTypeLabels } from "./queuePresentation";
import "../../styles/work-queue-v2.css";

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

const reasonOptions = [
  ["geometry", "Geometry"],
  ["class", "Wrong class"],
  ["missing_label", "Missing label"],
  ["tracking", "Tracking"],
  ["other", "Other"],
] as const;

function queueForRole(
  findings: Finding[],
  role: "reviewer" | "annotator" | "admin",
  userId: string,
) {
  if (role === "annotator") {
    return findings.filter(
      (finding) =>
        finding.assigneeId === userId &&
        ["assigned", "in_progress", "changes_requested"].includes(
          finding.workflowStage,
        ),
    );
  }
  if (role === "admin") {
    return findings.filter(
      (finding) => finding.riskScore >= 0.8 || finding.severity === "critical",
    );
  }
  return findings.filter((finding) =>
    ["submitted", "resubmitted", "in_review"].includes(finding.workflowStage),
  );
}

export function MockWorkQueueView({
  onOpenFinding,
  onOpenEditor,
}: {
  onOpenFinding?: (findingId: string) => void;
  onOpenEditor?: () => void;
}) {
  const { state, actions } = useMockData();
  const [query, setQuery] = useState("");
  const [view, setView] = useState<"mine" | "critical" | "rework">("mine");
  const [selectedId, setSelectedId] = useState("");
  const [feedbackOpen, setFeedbackOpen] = useState(false);
  const [feedback, setFeedback] = useState("");
  const [reason, setReason] =
    useState<(typeof reasonOptions)[number][0]>("geometry");
  const [reworkNote, setReworkNote] = useState("");

  const activeUser =
    state.users.find((user) => user.id === state.activeUserId) ??
    state.users[0];
  const roleQueue = useMemo(
    () => queueForRole(state.findings, state.activeRole, state.activeUserId),
    [state.activeRole, state.activeUserId, state.findings],
  );
  const visibleQueue = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return roleQueue
      .filter((finding) => {
        if (view === "critical" && finding.riskScore < 0.8) return false;
        if (
          view === "rework" &&
          !["changes_requested", "resubmitted"].includes(finding.workflowStage)
        )
          return false;
        if (!normalized) return true;
        return [finding.id, finding.title, finding.type, finding.trackId]
          .filter(Boolean)
          .join(" ")
          .toLowerCase()
          .includes(normalized);
      })
      .sort((first, second) => second.riskScore - first.riskScore);
  }, [query, roleQueue, view]);

  useEffect(() => {
    if (!visibleQueue.some((finding) => finding.id === selectedId)) {
      setSelectedId(visibleQueue[0]?.id ?? "");
    }
  }, [selectedId, visibleQueue]);

  useEffect(() => {
    setFeedbackOpen(false);
    setFeedback("");
    setReworkNote("");
  }, [selectedId]);

  const selected = visibleQueue.find((finding) => finding.id === selectedId);
  const selectedIndex = selected
    ? visibleQueue.findIndex((finding) => finding.id === selected.id)
    : -1;
  const frame = state.frames.find((item) => item.id === selected?.frameId);
  const batch = state.batches.find((item) => item.id === selected?.batchId);
  const assignee = state.users.find((item) => item.id === selected?.assigneeId);
  const evidence = selected
    ? state.evidences.filter((item) => selected.evidenceIds.includes(item.id))
    : [];
  const comments = selected
    ? state.feedbackComments.filter((item) => item.findingId === selected.id)
    : [];
  const annotator = state.users.find((user) => user.role === "annotator");

  const moveSelection = (offset: number) => {
    const next =
      visibleQueue[
        Math.min(Math.max(selectedIndex + offset, 0), visibleQueue.length - 1)
      ];
    if (next) setSelectedId(next.id);
  };

  const submitChanges = () => {
    if (!selected || !annotator || !feedback.trim()) return;
    actions.requestChanges(selected.id, annotator.id, feedback, reason);
    setFeedbackOpen(false);
    setFeedback("");
  };

  return (
    <div className="work-queue-page">
      <header className="work-queue-header">
        <div>
          <h1>
            {state.activeRole === "reviewer"
              ? "Review queue"
              : state.activeRole === "annotator"
                ? "My labeling queue"
                : "Agent attention queue"}
          </h1>
          <p>
            {batch?.name ?? "Active dataset"} · {visibleQueue.length} actionable
            tasks
          </p>
        </div>
        <div className="work-queue-header-actions">
          <Button
            variant="secondary"
            onClick={() => onOpenFinding?.(selected?.id ?? "")}
            disabled={!selected}
          >
            <MessageSquareText size={16} /> Activity
          </Button>
          <Button
            variant="primary"
            onClick={() =>
              selected &&
              moveSelection(selectedIndex < visibleQueue.length - 1 ? 1 : 0)
            }
            disabled={!selected}
          >
            Next task <ArrowRight size={16} />
          </Button>
        </div>
      </header>

      <div className="work-queue-toolbar">
        <div
          className="work-queue-views"
          role="tablist"
          aria-label="Queue views"
        >
          <button
            className={view === "mine" ? "is-active" : ""}
            type="button"
            onClick={() => setView("mine")}
          >
            My queue
          </button>
          <button
            className={view === "critical" ? "is-active" : ""}
            type="button"
            onClick={() => setView("critical")}
          >
            Critical
          </button>
          <button
            className={view === "rework" ? "is-active" : ""}
            type="button"
            onClick={() => setView("rework")}
          >
            Rework
          </button>
        </div>
        <label className="work-queue-search">
          <Search size={15} aria-hidden="true" />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search task, track or issue"
          />
          <kbd>/</kbd>
        </label>
        <button
          className="work-queue-filter-button"
          type="button"
          title="More filters"
          aria-label="More filters"
        >
          <SlidersHorizontal size={16} />
        </button>
      </div>

      <div className="work-queue-layout">
        <aside className="work-task-rail" aria-label="Actionable tasks">
          {visibleQueue.length ? (
            visibleQueue.map((finding) => {
              const itemFrame = state.frames.find(
                (item) => item.id === finding.frameId,
              );
              const unread = state.feedbackComments.filter(
                (item) => item.findingId === finding.id && !item.resolved,
              ).length;
              return (
                <button
                  className={`work-task-row ${finding.id === selectedId ? "is-selected" : ""}`}
                  type="button"
                  key={finding.id}
                  onClick={() => setSelectedId(finding.id)}
                >
                  {itemFrame ? (
                    <img src={itemFrame.thumbnailUrl} alt="" />
                  ) : (
                    <span className="work-task-placeholder" />
                  )}
                  <span className="work-task-copy">
                    <strong>{findingTypeLabels[finding.type]}</strong>
                    <small>
                      {finding.id} · {stageLabels[finding.workflowStage]}
                    </small>
                  </span>
                  <span
                    className={`work-task-risk severity-${finding.severity}`}
                  >
                    {Math.round(finding.riskScore * 100)}
                  </span>
                  {unread ? (
                    <span
                      className="work-task-comment"
                      aria-label={`${unread} unresolved comments`}
                    >
                      <MessageSquareText size={13} />
                      {unread}
                    </span>
                  ) : null}
                </button>
              );
            })
          ) : (
            <div className="work-queue-empty">
              <ShieldCheck size={24} />
              <strong>Queue is clear</strong>
              <span>No task matches this view.</span>
            </div>
          )}
        </aside>

        <main className="work-viewer-panel">
          <MockQueueComparisonViewer state={state} finding={selected} />
        </main>

        <aside className="work-action-rail">
          {selected ? (
            <>
              <div className="work-case-summary">
                <div>
                  <span
                    className={`workflow-stage stage-${selected.workflowStage}`}
                  >
                    {stageLabels[selected.workflowStage]}
                  </span>
                  <span
                    className={`severity-label severity-${selected.severity}`}
                  >
                    {selected.severity}
                  </span>
                </div>
                <h2>{selected.title}</h2>
                <dl>
                  <div>
                    <dt>Frame</dt>
                    <dd>{frame?.frameNumber ?? "—"}</dd>
                  </div>
                  <div>
                    <dt>Batch</dt>
                    <dd>{batch?.name ?? selected.batchId}</dd>
                  </div>
                  <div>
                    <dt>Owner</dt>
                    <dd>{assignee?.name ?? "Unassigned"}</dd>
                  </div>
                  <div>
                    <dt>Risk</dt>
                    <dd>{Math.round(selected.riskScore * 100)}/100</dd>
                  </div>
                </dl>
              </div>

              <section className="work-evidence-section">
                <h3>Evidence</h3>
                {evidence.map((item) => (
                  <div className="work-evidence-row" key={item.id}>
                    <span>{item.metric}</span>
                    <strong>{item.value}</strong>
                    <small>{item.threshold ?? item.kind}</small>
                  </div>
                ))}
              </section>

              <section className="work-comments-section">
                <h3>
                  Feedback <span>{comments.length}</span>
                </h3>
                {comments.length ? (
                  comments.map((comment: FeedbackComment) => {
                    const author = state.users.find(
                      (item) => item.id === comment.authorId,
                    );
                    return (
                      <div
                        className={`work-comment ${comment.resolved ? "is-resolved" : ""}`}
                        key={comment.id}
                      >
                        <div>
                          <strong>{author?.name ?? comment.authorId}</strong>
                          <span>rev {comment.annotationRevision ?? "—"}</span>
                        </div>
                        <p>{comment.body}</p>
                        <small>
                          {comment.reasonCategory.replaceAll("_", " ")} ·{" "}
                          {comment.resolved ? "Resolved" : "Blocking"}
                        </small>
                      </div>
                    );
                  })
                ) : (
                  <p className="work-empty-copy">
                    No reviewer feedback on this task.
                  </p>
                )}
              </section>

              <div className="work-decision-area">
                {state.activeRole === "reviewer" ? (
                  <>
                    {selected.workflowStage !== "in_review" ? (
                      <Button
                        variant="primary"
                        onClick={() =>
                          actions.setFindingStatus(
                            selected.id,
                            "in_review",
                            "start_review",
                          )
                        }
                      >
                        <Play size={16} /> Start review
                      </Button>
                    ) : (
                      <Button
                        variant="primary"
                        onClick={() =>
                          actions.approveFinding(
                            selected.id,
                            "Approved from focused queue",
                          )
                        }
                      >
                        <Check size={16} /> Approve
                      </Button>
                    )}
                    <Button
                      variant="secondary"
                      onClick={() => setFeedbackOpen((open) => !open)}
                    >
                      <RotateCcw size={16} /> Request changes
                    </Button>
                    <button
                      className="work-text-action"
                      type="button"
                      onClick={() =>
                        actions.setFindingStatus(
                          selected.id,
                          "rejected",
                          "reject_finding",
                          "Agent false positive",
                        )
                      }
                    >
                      <X size={15} /> Mark false positive
                    </button>
                  </>
                ) : state.activeRole === "annotator" ? (
                  <>
                    <Button variant="secondary" onClick={onOpenEditor}>
                      <PencilRuler size={16} /> Open editor
                    </Button>
                    {selected.workflowStage === "changes_requested" ? (
                      <>
                        <textarea
                          value={reworkNote}
                          onChange={(event) =>
                            setReworkNote(event.target.value)
                          }
                          placeholder="Summarize the correction"
                        />
                        <Button
                          variant="primary"
                          onClick={() =>
                            actions.resubmitFinding(selected.id, reworkNote)
                          }
                          disabled={!reworkNote.trim()}
                        >
                          Submit for review <ArrowRight size={16} />
                        </Button>
                      </>
                    ) : null}
                  </>
                ) : (
                  <Button
                    variant="primary"
                    onClick={() => actions.startQaRun(state.selectedDatasetId)}
                  >
                    <Play size={16} /> Run evaluation
                  </Button>
                )}
              </div>

              {feedbackOpen ? (
                <section className="work-feedback-form">
                  <div>
                    <CircleAlert size={17} />
                    <strong>Request correction</strong>
                  </div>
                  <label>
                    Reason
                    <select
                      value={reason}
                      onChange={(event) =>
                        setReason(event.target.value as typeof reason)
                      }
                    >
                      {reasonOptions.map(([value, label]) => (
                        <option key={value} value={value}>
                          {label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Assign to
                    <select defaultValue={annotator?.id}>
                      {annotator ? (
                        <option value={annotator.id}>{annotator.name}</option>
                      ) : null}
                    </select>
                  </label>
                  <label>
                    Feedback
                    <textarea
                      value={feedback}
                      onChange={(event) => setFeedback(event.target.value)}
                      placeholder="Describe the correction and expected result"
                    />
                  </label>
                  <div>
                    <Button
                      variant="ghost"
                      onClick={() => setFeedbackOpen(false)}
                    >
                      Cancel
                    </Button>
                    <Button
                      variant="primary"
                      onClick={submitChanges}
                      disabled={!feedback.trim()}
                    >
                      <UserRoundCheck size={16} /> Send to annotator
                    </Button>
                  </div>
                </section>
              ) : null}
            </>
          ) : null}
        </aside>
      </div>

      <footer className="work-queue-footer">
        <button
          type="button"
          onClick={() => moveSelection(-1)}
          disabled={selectedIndex <= 0}
          aria-label="Previous task"
        >
          <ChevronLeft size={16} />
        </button>
        <span>
          {selectedIndex >= 0 ? selectedIndex + 1 : 0} / {visibleQueue.length}
        </span>
        <button
          type="button"
          onClick={() => moveSelection(1)}
          disabled={
            selectedIndex < 0 || selectedIndex >= visibleQueue.length - 1
          }
          aria-label="Next task"
        >
          <ChevronRight size={16} />
        </button>
        <span className="work-queue-user">
          <UserRoundCheck size={14} />
          {activeUser?.name}
        </span>
      </footer>
    </div>
  );
}
