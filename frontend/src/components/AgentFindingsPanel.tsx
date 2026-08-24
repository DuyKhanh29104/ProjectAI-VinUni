import { Badge, Card, StatusBadge } from "./ui";
import type { Finding, MockState, Severity } from "../domain/types";

const severityLabels: Record<Severity, string> = {
  low: "Thấp",
  medium: "Trung bình",
  high: "Cao",
  critical: "Nghiêm trọng",
};

export function AgentFindingsPanel({
  state,
  finding,
}: {
  state: MockState;
  finding: Finding;
}) {
  const evidences = state.evidences.filter((evidence) => finding.evidenceIds.includes(evidence.id));
  const riskPercentage = Math.round(finding.riskScore * 100);

  return (
    <Card className="agent-findings-panel">
      <div className="agent-panel-heading">
        <div>
          <span className="eyebrow">AI quality finding</span>
          <h2>{finding.title}</h2>
        </div>
        <StatusBadge status={finding.status} />
      </div>

      <div className="risk-score-card">
        <div className="risk-score-heading">
          <span>Risk score</span>
          <strong className="selected-text">{finding.riskScore.toFixed(2)}</strong>
        </div>
        <div className="risk-score-track"><div className={`risk-score-fill fill-${finding.severity}`} style={{ width: `${riskPercentage}%` }} /></div>
        <div className="risk-score-footer"><span>{severityLabels[finding.severity]}</span><span>{riskPercentage}% confidence of issue</span></div>
      </div>

      <div className="agent-section">
        <span className="eyebrow">Explanation</span>
        <p className="agent-explanation">{finding.explanation}</p>
      </div>

      <div className="agent-section">
        <div className="agent-section-title"><span className="eyebrow">Evidence · {evidences.length}</span><Badge tone="info">Rule + model</Badge></div>
        <div className="agent-evidence-list">
          {evidences.map((evidence) => (
            <div className="agent-evidence-item" key={evidence.id}>
              <div className="evidence-icon">{evidence.kind.slice(0, 1).toUpperCase()}</div>
              <div>
                <div className="evidence-item-heading"><strong>{evidence.metric}</strong><span>{String(evidence.value)}</span></div>
                <p>{evidence.description}</p>
                {evidence.threshold ? <small>Threshold: {evidence.threshold}</small> : null}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="agent-recommendation">
        <span className="eyebrow">Recommended action</span>
        <p>{finding.recommendation}</p>
      </div>

      <div className="agent-provenance">
        <span>Model <strong>{finding.modelVersion}</strong></span>
        <span>Rule <strong>{finding.ruleVersion}</strong></span>
      </div>
    </Card>
  );
}
