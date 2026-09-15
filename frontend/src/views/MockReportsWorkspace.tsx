import { useMemo, useState } from "react";
import {
  ArrowRight,
  Download,
  Filter,
  ShieldCheck,
  TrendingDown,
} from "lucide-react";
import type {
  FindingType,
  MockState,
  TaskWorkflowStage,
} from "../domain/types";
import { findingTypeLabels } from "../features/qa-queue/queuePresentation";
import "../styles/reports-v2.css";

type ReportTab = "quality" | "operations" | "agent" | "release";

const stageOrder: TaskWorkflowStage[] = [
  "unassigned",
  "assigned",
  "in_progress",
  "submitted",
  "in_review",
  "changes_requested",
  "resubmitted",
  "approved",
];
const stageLabels: Record<TaskWorkflowStage, string> = {
  unassigned: "Unassigned",
  assigned: "Assigned",
  in_progress: "In progress",
  submitted: "Submitted",
  in_review: "In review",
  changes_requested: "Rework",
  resubmitted: "Resubmitted",
  approved: "Approved",
};

export function MockReportsWorkspace({ state }: { state: MockState }) {
  const [tab, setTab] = useState<ReportTab>("quality");
  const dataset = state.datasets.find(
    (item) => item.id === state.selectedDatasetId,
  );
  const findings = state.findings.filter(
    (item) => item.datasetId === state.selectedDatasetId,
  );
  const typeCounts = useMemo(
    () =>
      findings.reduce<Record<string, number>>((counts, finding) => {
        counts[finding.type] = (counts[finding.type] ?? 0) + 1;
        return counts;
      }, {}),
    [findings],
  );
  const stageCounts = useMemo(
    () =>
      findings.reduce<Record<string, number>>((counts, finding) => {
        counts[finding.workflowStage] =
          (counts[finding.workflowStage] ?? 0) + 1;
        return counts;
      }, {}),
    [findings],
  );
  const maxType = Math.max(...Object.values(typeCounts), 1);
  const approved = stageCounts.approved ?? 0;
  const rework = stageCounts.changes_requested ?? 0;
  const approvalRate = findings.length
    ? Math.round((approved / findings.length) * 100)
    : 100;
  const agreement = Math.round(
    (1 - state.reportMetrics.falsePositiveRate) * 100,
  );

  const exportSnapshot = () => {
    const content = JSON.stringify(
      {
        dataset,
        generatedAt: new Date().toISOString(),
        metrics: state.reportMetrics,
        findings,
      },
      null,
      2,
    );
    const url = URL.createObjectURL(
      new Blob([content], { type: "application/json" }),
    );
    const link = document.createElement("a");
    link.href = url;
    link.download = `label-guardian-${dataset?.id ?? "report"}.json`;
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="reports-v2-page">
      <header className="reports-v2-header">
        <div>
          <h1>Reports</h1>
          <p>
            {dataset?.name} / {dataset?.version}
          </p>
        </div>
        <div className="reports-v2-actions">
          <button type="button">
            <Filter size={15} /> Last 30 days
          </button>
          <button type="button" onClick={exportSnapshot}>
            <Download size={15} /> Export
          </button>
        </div>
      </header>

      <nav className="reports-v2-tabs" aria-label="Report questions">
        {(["quality", "operations", "agent", "release"] as ReportTab[]).map(
          (item) => (
            <button
              className={tab === item ? "is-active" : ""}
              type="button"
              key={item}
              onClick={() => setTab(item)}
            >
              {item[0].toUpperCase() + item.slice(1)}
            </button>
          ),
        )}
      </nav>

      <section className="reports-v2-metrics" aria-label="Report summary">
        <div>
          <span>Post-QA quality</span>
          <strong>
            {Math.round((1 - state.reportMetrics.afterQaErrorRate) * 100)}%
          </strong>
          <small>
            <TrendingDown size={13} />{" "}
            {Math.round(
              (state.reportMetrics.beforeQaErrorRate -
                state.reportMetrics.afterQaErrorRate) *
                100,
            )}{" "}
            points improved
          </small>
        </div>
        <div>
          <span>Approval progress</span>
          <strong>{approvalRate}%</strong>
          <small>
            {approved} of {findings.length} cases
          </small>
        </div>
        <div>
          <span>Rework rate</span>
          <strong>
            {findings.length ? Math.round((rework / findings.length) * 100) : 0}
            %
          </strong>
          <small>{rework} blocking returns</small>
        </div>
        <div>
          <span>Reviewer / agent agreement</span>
          <strong>{agreement}%</strong>
          <small>
            {state.reportMetrics.falsePositiveRate * 100}% false positive
          </small>
        </div>
      </section>

      {tab === "quality" ? (
        <div className="reports-v2-grid">
          <section className="reports-v2-panel reports-quality-trend">
            <header>
              <div>
                <h2>Quality trend</h2>
                <p>Error rate before and after human review.</p>
              </div>
              <span>6 runs</span>
            </header>
            <div
              className="quality-trend-chart"
              aria-label="Quality trend over six runs"
            >
              {[18, 16, 15, 13, 10, 7].map((value, index) => (
                <div key={index}>
                  <i style={{ height: `${Math.max(value * 4, 20)}px` }} />
                  <strong>{value}%</strong>
                  <small>R{index + 1}</small>
                </div>
              ))}
            </div>
            <div className="quality-target">
              <ShieldCheck size={15} />
              <span>Release threshold</span>
              <strong>&lt; 8% error rate</strong>
            </div>
          </section>
          <section className="reports-v2-panel">
            <header>
              <div>
                <h2>Issue mix</h2>
                <p>Cases by detected failure mode.</p>
              </div>
            </header>
            <div className="reports-bar-list">
              {Object.entries(typeCounts)
                .sort(([, a], [, b]) => b - a)
                .map(([type, count]) => (
                  <button type="button" key={type}>
                    <span>{findingTypeLabels[type as FindingType]}</span>
                    <i>
                      <b style={{ width: `${(count / maxType) * 100}%` }} />
                    </i>
                    <strong>{count}</strong>
                    <ArrowRight size={14} />
                  </button>
                ))}
            </div>
          </section>
        </div>
      ) : null}

      {tab === "operations" ? (
        <div className="reports-v2-grid">
          <section className="reports-v2-panel reports-flow-panel">
            <header>
              <div>
                <h2>Case flow</h2>
                <p>Current workload across workflow stages.</p>
              </div>
            </header>
            <div className="reports-flow">
              {stageOrder.map((stage) => (
                <div key={stage}>
                  <strong>{stageCounts[stage] ?? 0}</strong>
                  <span>{stageLabels[stage]}</span>
                  <i
                    style={{
                      height: `${Math.max(10, (stageCounts[stage] ?? 0) * 28)}px`,
                    }}
                  />
                </div>
              ))}
            </div>
          </section>
          <section className="reports-v2-panel">
            <header>
              <div>
                <h2>Workload</h2>
                <p>Assignments and outcomes by operator.</p>
              </div>
            </header>
            <div className="reports-people">
              {state.users
                .filter((user) => user.role !== "admin")
                .map((user) => {
                  const assigned = findings.filter(
                    (finding) => finding.assigneeId === user.id,
                  );
                  const done = assigned.filter(
                    (finding) => finding.workflowStage === "approved",
                  ).length;
                  return (
                    <div key={user.id}>
                      <span className="avatar">{user.avatarInitials}</span>
                      <span>
                        <strong>{user.name}</strong>
                        <small>{user.role}</small>
                      </span>
                      <i>
                        <b
                          style={{
                            width: `${assigned.length ? (done / assigned.length) * 100 : 0}%`,
                          }}
                        />
                      </i>
                      <strong>
                        {done}/{assigned.length}
                      </strong>
                    </div>
                  );
                })}
            </div>
          </section>
        </div>
      ) : null}

      {tab === "agent" ? (
        <div className="reports-v2-grid">
          <section className="reports-v2-panel reports-agent-score">
            <header>
              <div>
                <h2>Agent calibration</h2>
                <p>Human decisions against generated cases.</p>
              </div>
            </header>
            <div
              className="agent-score-ring"
              style={
                { "--score": `${agreement * 3.6}deg` } as React.CSSProperties
              }
            >
              <span>
                <strong>{agreement}%</strong>
                <small>agreement</small>
              </span>
            </div>
            <dl>
              <div>
                <dt>Precision</dt>
                <dd>{Math.round(state.reportMetrics.precision * 100)}%</dd>
              </div>
              <div>
                <dt>Recall</dt>
                <dd>{Math.round(state.reportMetrics.recall * 100)}%</dd>
              </div>
              <div>
                <dt>F1</dt>
                <dd>{Math.round(state.reportMetrics.f1Score * 100)}%</dd>
              </div>
            </dl>
          </section>
          <section className="reports-v2-panel">
            <header>
              <div>
                <h2>Calibration watchlist</h2>
                <p>Signals that need ML engineer attention.</p>
              </div>
            </header>
            <div className="calibration-list">
              <button type="button">
                <span>Wrong class rule</span>
                <small>3 reviewer disagreements</small>
                <strong>Inspect</strong>
              </button>
              <button type="button">
                <span>YOLO reference</span>
                <small>Confidence drift on night scenes</small>
                <strong>Compare</strong>
              </button>
              <button type="button">
                <span>Temporal continuity</span>
                <small>Stable across latest run</small>
                <strong className="is-healthy">Healthy</strong>
              </button>
            </div>
          </section>
        </div>
      ) : null}

      {tab === "release" ? (
        <section className="reports-v2-panel release-readiness">
          <header>
            <div>
              <h2>Release readiness</h2>
              <p>Quality gates for {dataset?.version}.</p>
            </div>
            <strong>
              {approvalRate >= 80 ? "Ready with blockers" : "Review required"}
            </strong>
          </header>
          <div>
            {[
              "Agent evaluation complete",
              "Critical cases resolved",
              "Blocking feedback closed",
              "Dataset revision frozen",
            ].map((label, index) => (
              <span className={index < 2 ? "is-complete" : ""} key={label}>
                <i>{index < 2 ? "OK" : index + 1}</i>
                <strong>{label}</strong>
                <small>{index < 2 ? "Passed" : "Pending"}</small>
              </span>
            ))}
          </div>
        </section>
      ) : null}
    </div>
  );
}
