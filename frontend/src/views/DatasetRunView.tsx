import { Badge, Button, Card, SectionHeading, StatCard } from "../components/ui";
import { useMockData } from "../state/MockDataProvider";

function displayTime(value?: string) {
  return value ? new Date(value).toLocaleString("vi-VN") : "—";
}

export function DatasetRunView() {
  const { state, actions } = useMockData();
  const dataset = state.datasets.find((item) => item.id === state.selectedDatasetId) ?? state.datasets[0];
  const scenes = state.scenes.filter((scene) => scene.datasetId === dataset.id);
  const frames = state.frames.filter((frame) => scenes.some((scene) => scene.id === frame.sceneId));
  const annotations = state.annotations.filter((annotation) => annotation.layer === "original" && frames.some((frame) => frame.id === annotation.frameId));
  const findings = state.findings.filter((finding) => scenes.some((scene) => scene.id === finding.sceneId));
  const run = state.qaRun.datasetId === dataset.id
    ? state.qaRun
    : { ...state.qaRun, datasetId: dataset.id, status: "idle" as const, progress: 0, processedFrames: 0, totalFrames: frames.length };
  const activeModels = state.models.filter((model) => model.enabled);
  const activeRules = state.rules.filter((rule) => rule.enabled);

  return (
    <div className="page-container view-page dataset-run-page">
      <div className="page-heading">
        <div>
          <span className="eyebrow">Dataset operations</span>
          <h1>Datasets / Runs</h1>
          <p className="page-description">Theo dõi phiên bản dataset, phạm vi frame và tiến trình chạy QA mô phỏng trước khi kết nối backend thật.</p>
        </div>
        <div className="page-heading-actions">
          <Badge tone={dataset.anonymized ? "success" : "high"}>{dataset.anonymized ? "Anonymized dataset" : "Privacy review needed"}</Badge>
          <Badge tone="info">{dataset.version}</Badge>
        </div>
      </div>

      <Card className="privacy-safe-card">
        <div className="privacy-safe-icon">✓</div>
        <div><strong>Safe mock mode</strong><p>QA run chỉ cập nhật progress trong frontend state. Không có model inference thật và không ghi đè ground truth.</p></div>
        <Badge tone="success">No backend write</Badge>
      </Card>

      <section className="dataset-run-kpi-grid">
        <StatCard label="Dataset version" value={dataset.version.split("@").pop() ?? dataset.version} detail={dataset.format} tone="blue" />
        <StatCard label="Scenes" value={scenes.length} detail="Sequence trong version" tone="purple" />
        <StatCard label="Frames" value={frames.length} detail={`${run.processedFrames} đã chạy trong mock run`} tone="orange" />
        <StatCard label="Flagged findings" value={findings.length} detail="Case từ agent mock" tone="green" />
      </section>

      <div className="dataset-run-grid">
        <Card className="qa-run-progress-card">
          <div className="qa-run-heading"><SectionHeading eyebrow="Mock execution" title="QA run progress" description="Tiến trình giả lập theo từng bước 25%; không chạy model thật." /><Badge tone={run.status === "completed" ? "success" : run.status === "running" ? "info" : "neutral"}>{run.status === "completed" ? "Completed" : run.status === "running" ? "Running" : "Ready"}</Badge></div>
          <div className="qa-run-progress-value"><strong>{run.progress}%</strong><span>{run.processedFrames}/{run.totalFrames} frames</span></div>
          <div className="progress-track qa-run-track"><div className="progress-fill progress-blue" style={{ width: `${run.progress}%` }} /></div>
          <div className="qa-run-actions">
            <Button variant="primary" onClick={() => actions.startQaRun(dataset.id)} disabled={run.status === "running"}>{run.status === "completed" ? "Chạy lại mock QA" : "Start mock QA run"}</Button>
            <Button variant="secondary" onClick={actions.advanceQaRun} disabled={run.status !== "running"}>Advance +25%</Button>
          </div>
          <div className="qa-run-meta"><span>Run ID <strong>{run.id}</strong></span><span>Started <strong>{displayTime(run.startedAt)}</strong></span><span>Completed <strong>{displayTime(run.completedAt)}</strong></span><span>Duration <strong>{run.durationSeconds ? `${run.durationSeconds}s` : "—"}</strong></span></div>
        </Card>

        <Card className="qa-run-config-card">
          <SectionHeading eyebrow="Resolved configuration" title="Model và rules đang dùng" description="Snapshot cấu hình mock được gắn vào run khi bắt đầu." />
          <div className="qa-run-config-list"><div><span>Model</span><strong>{activeModels.map((model) => model.version).join(", ") || "No model enabled"}</strong></div><div><span>Rules</span><strong>{activeRules.length} enabled</strong></div><div><span>Rule snapshot</span><strong>{run.ruleVersion}</strong></div><div><span>Privacy</span><strong>{dataset.anonymized ? "Anonymized" : "Review required"}</strong></div></div>
        </Card>
      </div>

      <Card className="dataset-scene-card">
        <SectionHeading eyebrow="Dataset scope" title="Scenes trong version đang chọn" description="Thông tin read-only lấy từ mock dataset manifest." />
        <div className="dataset-scene-list">{scenes.map((scene) => { const sceneFrames = frames.filter((frame) => frame.sceneId === scene.id); const sceneAnnotations = annotations.filter((annotation) => sceneFrames.some((frame) => frame.id === annotation.frameId)); return <div className="dataset-scene-row" key={scene.id}><div><strong>{scene.name}</strong><small>{scene.location} · {scene.weather}</small></div><span>{sceneFrames.length} frames</span><span>{sceneAnnotations.length} annotations</span><Badge tone="success">{scene.annotatorId}</Badge></div>; })}</div>
      </Card>
    </div>
  );
}
