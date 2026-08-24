import { useEffect, useState } from "react";
import { AgentFindingsPanel } from "../components/AgentFindingsPanel";
import { Button, Card, Badge, StatusBadge } from "../components/ui";
import { FrameViewer } from "../components/FrameViewer";
import { ReviewActions } from "../components/ReviewActions";
import { SequenceTimeline } from "../components/SequenceTimeline";
import { AnnotationEditPanel } from "../components/AnnotationEditPanel";
import { ReviewHistoryPanel } from "../components/ReviewHistoryPanel";
import { useMockData } from "../state/MockDataProvider";

export function CaseDetailView({
  findingId,
  onBack,
  onEditLabels,
}: {
  findingId: string;
  onBack: () => void;
  onEditLabels: () => void;
}) {
  const { state } = useMockData();
  const finding = state.findings.find((item) => item.id === findingId);
  const [selectedFrameId, setSelectedFrameId] = useState(finding?.frameId ?? "");

  useEffect(() => {
    setSelectedFrameId(finding?.frameId ?? "");
  }, [finding?.frameId, finding?.id]);

  if (!finding) {
    return (
      <div className="page-container view-page">
        <Button variant="ghost" onClick={onBack}>← Quay lại QA Queue</Button>
        <Card className="case-not-found-card">
          <div className="empty-state-icon">?</div>
          <h1>Không tìm thấy QA case</h1>
          <p className="muted">Case {findingId} không tồn tại trong mock repository.</p>
        </Card>
      </div>
    );
  }

  const frame = state.frames.find((item) => item.id === selectedFrameId);
  const scene = state.scenes.find((item) => item.id === finding.sceneId);
  const originalAnnotation = state.annotations.find(
    (annotation) => annotation.id === finding.annotationId && annotation.layer === "original",
  );
  const prediction = state.predictions.find(
    (item) => item.frameId === finding.frameId && item.trackId === finding.trackId,
  );

  return (
    <div className="page-container view-page case-detail-page">
      <div className="case-breadcrumb">
        <Button variant="ghost" size="sm" onClick={onBack}>← QA Queue</Button>
        <span>/</span>
        <span>{finding.id}</span>
      </div>

      <div className="case-heading">
        <div>
          <div className="case-heading-kicker">
            <span className="eyebrow">AI-assisted annotation review</span>
            <Badge tone={finding.severity}>{finding.severity.toUpperCase()}</Badge>
            <StatusBadge status={finding.status} />
            <Badge tone="info">2D QA evidence</Badge>
          </div>
          <h1>{finding.title}</h1>
          <p className="page-description">{finding.summary}</p>
        </div>
        <div className="case-risk-summary">
          <span className="eyebrow">Risk score</span>
          <strong className="selected-text">{finding.riskScore.toFixed(2)}</strong>
          <span>{finding.priority <= 2 ? "Ưu tiên review cao" : `Priority P${finding.priority}`}</span>
          <Button variant="secondary" size="sm" onClick={onEditLabels}>Edit in Label Editor</Button>
        </div>
      </div>

      <div className="case-metadata-strip">
        <div><span>Scene</span><strong>{scene?.name ?? finding.sceneId}</strong></div>
        <div><span>Frame</span><strong>{frame?.frameNumber ?? "—"}</strong></div>
        <div><span>Track ID</span><strong>{finding.trackId ?? "Không có"}</strong></div>
        <div><span>Nhãn gốc</span><strong>{originalAnnotation?.label ?? "Missing object"}</strong></div>
        <div><span>Prediction</span><strong>{prediction ? `${prediction.label} · ${Math.round(prediction.confidence * 100)}%` : "Không có"}</strong></div>
        <div><span>Frame size</span><strong>{frame ? `${frame.width}×${frame.height}` : "—"}</strong></div>
        <div><span>Dataset version</span><strong>{finding.datasetVersion}</strong></div>
        <div><span>QA run</span><strong>{finding.qaRunId}</strong></div>
      </div>

      <div className="case-main-grid">
        <Card className="case-viewer-card">
          <FrameViewer state={state} finding={finding} frameId={selectedFrameId} />
          <SequenceTimeline
            state={state}
            finding={finding}
            selectedFrameId={selectedFrameId}
            onFrameChange={setSelectedFrameId}
          />
        </Card>
        <div className="case-evidence-column">
          <AgentFindingsPanel state={state} finding={finding} />
          <ReviewActions state={state} finding={finding} />
        </div>
      </div>

      <AnnotationEditPanel state={state} finding={finding} />
      <ReviewHistoryPanel state={state} finding={finding} />
    </div>
  );
}
