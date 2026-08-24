import { useEffect, useMemo, useState } from "react";
import { Badge, Button, Card, SectionHeading, StatCard } from "../components/ui";
import type { FindingType, MockState, Severity } from "../domain/types";

const findingTypeLabels: Record<FindingType, string> = {
  box_misalignment: "Box lệch vị trí",
  wrong_class: "Sai class",
  missing_object: "Thiếu object",
  duplicate_annotation: "Annotation trùng",
  track_id_switch: "ID switch",
  track_break: "Track bị đứt",
  temporal_inconsistency: "Không nhất quán thời gian",
};

const severityLabels: Record<Severity, string> = {
  low: "Thấp",
  medium: "Trung bình",
  high: "Cao",
  critical: "Nghiêm trọng",
};

export function ReportsView({ state }: { state: MockState }) {
  const [exportFormat, setExportFormat] = useState<"json" | "csv">("json");
  const [exportState, setExportState] = useState<"idle" | "exporting" | "success">("idle");
  const selectedSceneIds = new Set(state.scenes.filter((scene) => scene.datasetId === state.selectedDatasetId).map((scene) => scene.id));
  const findings = state.findings.filter((finding) => selectedSceneIds.has(finding.sceneId));
  const selectedDataset = state.datasets.find((dataset) => dataset.id === state.selectedDatasetId);
  const selectedFrameIds = new Set(state.frames.filter((frame) => selectedSceneIds.has(frame.sceneId)).map((frame) => frame.id));
  const originalAnnotations = state.annotations.filter((annotation) => annotation.layer === "original" && selectedFrameIds.has(annotation.frameId));
  const typeCounts = useMemo(() => findings.reduce<Record<string, number>>((counts, finding) => { counts[finding.type] = (counts[finding.type] ?? 0) + 1; return counts; }, {}), [findings]);
  const severityCounts = useMemo(() => findings.reduce<Record<string, number>>((counts, finding) => { counts[finding.severity] = (counts[finding.severity] ?? 0) + 1; return counts; }, {}), [findings]);
  const classCounts = useMemo(() => originalAnnotations.reduce<Record<string, number>>((counts, annotation) => { counts[annotation.label] = (counts[annotation.label] ?? 0) + 1; return counts; }, {}), [originalAnnotations]);
  const sceneCounts = useMemo(() => findings.reduce<Record<string, number>>((counts, finding) => { counts[finding.sceneId] = (counts[finding.sceneId] ?? 0) + 1; return counts; }, {}), [findings]);
  const annotatorStats = state.users.map((user) => {
    const assigned = findings.filter((finding) => finding.assigneeId === user.id);
    const completed = assigned.filter((finding) => ["confirmed", "corrected", "rejected"].includes(finding.status)).length;
    return { user, assigned: assigned.length, completed, rate: assigned.length ? completed / assigned.length : 0 };
  }).filter((row) => row.assigned > 0);
  const maxTypeCount = Math.max(...Object.values(typeCounts), 1);
  const maxSeverityCount = Math.max(...Object.values(severityCounts), 1);
  const maxClassCount = Math.max(...Object.values(classCounts), 1);
  const maxSceneCount = Math.max(...Object.values(sceneCounts), 1);
  const exportRows = findings.map((finding) => ({
    findingId: finding.id,
    sceneId: finding.sceneId,
    frameId: finding.frameId,
    type: finding.type,
    severity: finding.severity,
    riskScore: finding.riskScore,
    status: finding.status,
    assigneeId: finding.assigneeId ?? "unassigned",
  }));

  useEffect(() => {
    if (exportState !== "success") {
      return;
    }
    const timeoutId = window.setTimeout(() => setExportState("idle"), 3200);
    return () => window.clearTimeout(timeoutId);
  }, [exportState]);

  const handleExport = () => {
    if (!selectedDataset) {
      return;
    }
    setExportState("exporting");
    window.setTimeout(() => {
      const metadata = {
        datasetId: selectedDataset.id,
        datasetVersion: selectedDataset.version,
        generatedAt: new Date().toISOString(),
        source: "Label Guardian mock frontend",
        filters: { datasetId: selectedDataset.id },
      };
      const content = exportFormat === "json"
        ? JSON.stringify({ metadata, rows: exportRows }, null, 2)
        : [
            "findingId,sceneId,frameId,type,severity,riskScore,status,assigneeId",
            ...exportRows.map((row) => [row.findingId, row.sceneId, row.frameId, row.type, row.severity, row.riskScore, row.status, row.assigneeId].map((value) => `"${String(value).replaceAll('"', '""')}"`).join(",")),
          ].join("\n");
      const blob = new Blob([content], { type: exportFormat === "json" ? "application/json" : "text/csv;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `label-guardian-${selectedDataset.id}-report.${exportFormat}`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      setExportState("success");
    }, 420);
  };

  return (
    <div className="page-container view-page reports-page">
      <div className="page-heading">
        <div><span className="eyebrow">Dataset quality analytics</span><h1>Báo cáo chất lượng dataset</h1><p className="page-description">Tổng hợp hiệu quả phát hiện lỗi và review cho {selectedDataset?.name}.</p></div>
        <div className="page-heading-actions"><Badge tone="info">{selectedDataset?.version}</Badge><Badge tone="success">Mock export</Badge></div>
      </div>

      <Card className="report-export-card">
        <div><span className="eyebrow">Report export</span><strong>Xuất snapshot theo dataset/filter hiện tại</strong><small>File được tạo ngay trong browser, không gửi dữ liệu ra ngoài.</small></div>
        <div className="report-export-controls">
          <label><span>Định dạng</span><select value={exportFormat} onChange={(event) => setExportFormat(event.target.value as "json" | "csv")}><option value="json">JSON</option><option value="csv">CSV</option></select></label>
          <Button variant="primary" onClick={handleExport} disabled={exportState === "exporting"}>{exportState === "exporting" ? "Đang tạo file…" : "Tải report mock"}</Button>
        </div>
        <div className={`report-export-status report-export-status-${exportState}`} role="status">{exportState === "success" ? "✓ Đã tạo file với dataset version và filter hiện tại" : exportState === "exporting" ? "Đang đóng gói dữ liệu mock…" : `${exportRows.length} finding sẽ được xuất`}</div>
      </Card>

      <section className="reports-kpi-grid">
        <StatCard label="QA score" value={`${Math.round((1 - state.reportMetrics.afterQaErrorRate) * 100)}%`} detail="Dataset quality after review" tone="blue" />
        <StatCard label="Recall" value={`${Math.round(state.reportMetrics.recall * 100)}%`} detail="Lỗi đã được phát hiện" tone="purple" />
        <StatCard label="F1-score" value={`${Math.round(state.reportMetrics.f1Score * 100)}%`} detail="Cân bằng precision/recall" tone="green" />
        <StatCard label="Review time" value={`${state.reportMetrics.averageReviewSeconds}s`} detail={`${state.reportMetrics.savedReviewHours}h tiết kiệm`} tone="orange" />
      </section>

      <div className="reports-grid">
        <Card>
          <SectionHeading eyebrow="Error distribution" title="Phân bố theo loại lỗi" description="Số case bị gắn cờ trong dataset đang chọn." />
          <div className="report-bar-list">{Object.entries(typeCounts).sort(([, first], [, second]) => second - first).map(([type, count]) => <div className="report-bar-row" key={type}><div><span>{findingTypeLabels[type as FindingType]}</span><strong>{count}</strong></div><div className="progress-track"><div className="progress-fill progress-blue" style={{ width: `${(count / maxTypeCount) * 100}%` }} /></div></div>)}</div>
        </Card>
        <Card>
          <SectionHeading eyebrow="Severity" title="Mức độ rủi ro" description="Theo dõi các nhóm cần ưu tiên review." />
          <div className="severity-report-list">{(["critical", "high", "medium", "low"] as Severity[]).map((severity) => { const count = severityCounts[severity] ?? 0; return <div className="severity-report-row" key={severity}><Badge tone={severity}>{severityLabels[severity]}</Badge><div className="progress-track"><div className={`progress-fill progress-${severity}`} style={{ width: `${(count / maxSeverityCount) * 100}%` }} /></div><strong>{count}</strong></div>; })}</div>
          <div className="before-after-card"><div><span>Trước QA</span><strong>{Math.round(state.reportMetrics.beforeQaErrorRate * 100)}%</strong></div><span>→</span><div><span>Sau QA</span><strong className="selected-text">{Math.round(state.reportMetrics.afterQaErrorRate * 100)}%</strong></div></div>
        </Card>
      </div>

      <div className="reports-grid reports-grid-secondary">
        <Card>
          <SectionHeading eyebrow="Annotation classes" title="Phân bố theo class" description="Nhãn gốc trong các frame thuộc dataset đang chọn." />
          <div className="report-bar-list">{Object.entries(classCounts).sort(([, first], [, second]) => second - first).map(([label, count]) => <div className="report-bar-row" key={label}><div><span>{label}</span><strong>{count}</strong></div><div className="progress-track"><div className="progress-fill progress-purple" style={{ width: `${(count / maxClassCount) * 100}%` }} /></div></div>)}</div>
        </Card>
        <Card>
          <SectionHeading eyebrow="Scene workload" title="Phân bố theo scene" description="Số finding cần xử lý trong từng sequence." />
          <div className="report-bar-list">{Object.entries(sceneCounts).sort(([, first], [, second]) => second - first).map(([sceneId, count]) => <div className="report-bar-row" key={sceneId}><div><span>{state.scenes.find((scene) => scene.id === sceneId)?.name ?? sceneId}</span><strong>{count}</strong></div><div className="progress-track"><div className="progress-fill progress-blue" style={{ width: `${(count / maxSceneCount) * 100}%` }} /></div></div>)}</div>
        </Card>
      </div>

      <div className="reports-grid reports-grid-bottom">
        <Card>
          <SectionHeading eyebrow="Annotator performance" title="Phân bố task theo người xử lý" description="Metric mock theo case được gán và đã có quyết định." />
          <div className="annotator-report-table"><div className="annotator-report-head"><span>Người xử lý</span><span>Assigned</span><span>Completed</span><span>Rate</span></div>{annotatorStats.map((row) => <div className="annotator-report-row" key={row.user.id}><div className="annotator-report-user"><span className="avatar">{row.user.avatarInitials}</span><span><strong>{row.user.name}</strong><small>{row.user.role}</small></span></div><span>{row.assigned}</span><span>{row.completed}</span><strong className="selected-text">{Math.round(row.rate * 100)}%</strong></div>)}</div>
        </Card>
        <Card>
          <SectionHeading eyebrow="High-risk cases" title="Top risk cần xử lý" description="Danh sách lấy theo risk score từ mock agent." />
          <div className="report-risk-list">{[...findings].sort((first, second) => second.riskScore - first.riskScore).slice(0, 5).map((finding) => <div className="report-risk-row" key={finding.id}><span className="priority-pill">P{finding.priority}</span><div><strong>{finding.id}</strong><small>{findingTypeLabels[finding.type]}</small></div><Badge tone={finding.severity}>{finding.riskScore.toFixed(2)}</Badge></div>)}</div>
        </Card>
      </div>

      <Card className="report-method-card"><span className="eyebrow">Report metadata</span><div><span>Dataset version <strong>{selectedDataset?.version}</strong></span><span>Model <strong>yolo-reference@2026.08</strong></span><span>Rules <strong>geometry + temporal + context</strong></span><span>Generated <strong>Mock run · 06/08/2026</strong></span></div></Card>
    </div>
  );
}
