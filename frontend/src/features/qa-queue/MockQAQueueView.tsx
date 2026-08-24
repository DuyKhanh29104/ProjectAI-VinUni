import { useEffect, useMemo, useState } from "react";
import { Badge, Button, Card, StatusBadge } from "../../components/ui";
import { filterAndSortFindings, type QueueSortKey } from "../../domain/queueUtils";
import type { FindingType, ReviewStatus, Severity } from "../../domain/types";
import { useMockData } from "../../state/MockDataProvider";
import { MockQueueComparisonViewer } from "./components/MockQueueComparisonViewer";
import { QueueAnalytics } from "./QueueAnalytics";
import {
  findingTypeLabels,
  QueueKpiCard,
  reviewStatuses,
  statusLabels,
} from "./queuePresentation";

const PAGE_SIZE = 10;

export function MockQAQueueView({
  onOpenFinding,
  onOpenEditor,
}: {
  onOpenFinding?: (findingId: string) => void;
  onOpenEditor?: () => void;
}) {
  const { state, actions } = useMockData();
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<ReviewStatus | "all">("all");
  const [severityFilter, setSeverityFilter] = useState<Severity | "all">("all");
  const [typeFilter, setTypeFilter] = useState<FindingType | "all">("all");
  const [sceneFilter, setSceneFilter] = useState("all");
  const [frameFilter, setFrameFilter] = useState("");
  const [classFilter, setClassFilter] = useState("all");
  const [annotatorFilter, setAnnotatorFilter] = useState("all");
  const [minimumRisk, setMinimumRisk] = useState(0);
  const [sortBy, setSortBy] = useState<QueueSortKey>("priority");
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [selectedFindingId, setSelectedFindingId] = useState("");
  const [bulkAssigneeId, setBulkAssigneeId] = useState("user-reviewer");
  const [page, setPage] = useState(1);

  const selectedDataset = state.datasets.find(
    (dataset) => dataset.id === state.selectedDatasetId,
  );
  const selectedDatasetSceneIds = useMemo(
    () =>
      new Set(
        state.scenes
          .filter((scene) => scene.datasetId === state.selectedDatasetId)
          .map((scene) => scene.id),
      ),
    [state.scenes, state.selectedDatasetId],
  );
  const selectedDatasetFindings = state.findings.filter((finding) =>
    selectedDatasetSceneIds.has(finding.sceneId),
  );
  const sceneOptions = state.scenes.filter((scene) =>
    selectedDatasetSceneIds.has(scene.id),
  );
  const classOptions = useMemo(
    () =>
      [...new Set(
        state.annotations
          .filter((annotation) => {
            const frame = state.frames.find((item) => item.id === annotation.frameId);
            return annotation.layer === "original" && Boolean(frame && selectedDatasetSceneIds.has(frame.sceneId));
          })
          .map((annotation) => annotation.label),
      )].sort(),
    [selectedDatasetSceneIds, state.annotations, state.frames],
  );

  const visibleFindings = useMemo(() => {
    const searchTextByFindingId = new Map(
      state.findings.map((finding) => {
        const scene = state.scenes.find((item) => item.id === finding.sceneId);
        const frame = state.frames.find((item) => item.id === finding.frameId);
        const annotation = state.annotations.find(
          (item) => item.id === finding.annotationId && item.layer === "original",
        );
        return [
          finding.id,
          [
            finding.id,
            finding.title,
            finding.summary,
            finding.type,
            finding.trackId,
            scene?.name,
            frame ? `frame ${frame.frameNumber}` : undefined,
            annotation?.label,
          ]
            .filter(Boolean)
            .join(" "),
        ] as const;
      }),
    );

    return filterAndSortFindings(state.findings, {
      query,
      status: statusFilter,
      severity: severityFilter,
      type: typeFilter,
      sceneId: sceneFilter,
      risk: "all",
      sortBy,
      sceneIds: selectedDatasetSceneIds,
      searchTextByFindingId,
    }).filter((finding) => {
      const frame = state.frames.find((item) => item.id === finding.frameId);
      const annotation = state.annotations.find(
        (item) => item.id === finding.annotationId && item.layer === "original",
      );
      return (
        finding.riskScore * 100 >= minimumRisk &&
        (frameFilter.trim() === "" || String(frame?.frameNumber ?? "").includes(frameFilter.trim())) &&
        (classFilter === "all" || annotation?.label === classFilter) &&
        (annotatorFilter === "all" || finding.assigneeId === annotatorFilter)
      );
    });
  }, [
    annotatorFilter,
    classFilter,
    frameFilter,
    minimumRisk,
    query,
    sceneFilter,
    severityFilter,
    selectedDatasetSceneIds,
    sortBy,
    state.annotations,
    state.findings,
    state.frames,
    state.scenes,
    statusFilter,
    typeFilter,
  ]);

  const pageCount = Math.max(1, Math.ceil(visibleFindings.length / PAGE_SIZE));
  const pagedFindings = visibleFindings.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  useEffect(() => {
    setPage(1);
  }, [annotatorFilter, classFilter, frameFilter, minimumRisk, query, sceneFilter, severityFilter, sortBy, state.selectedDatasetId, statusFilter, typeFilter]);

  useEffect(() => {
    setPage((current) => Math.min(current, pageCount));
  }, [pageCount]);

  useEffect(() => {
    if (!visibleFindings.some((finding) => finding.id === selectedFindingId)) {
      setSelectedFindingId(visibleFindings[0]?.id ?? "");
    }
  }, [selectedFindingId, visibleFindings]);

  const selectedFinding = visibleFindings.find(
    (finding) => finding.id === selectedFindingId,
  );
  const selectedScene = state.scenes.find((scene) => scene.id === selectedFinding?.sceneId);
  const selectedFrame = state.frames.find((frame) => frame.id === selectedFinding?.frameId);
  const selectedAnnotation = state.annotations.find(
    (annotation) =>
      annotation.id === selectedFinding?.annotationId && annotation.layer === "original",
  );
  const selectedEvidence = selectedFinding
    ? state.evidences.filter((evidence) => selectedFinding.evidenceIds.includes(evidence.id))
    : [];
  const canReview = state.activeRole === "reviewer";
  const allVisibleSelected =
    pagedFindings.length > 0 &&
    pagedFindings.every((finding) => selectedIds.includes(finding.id));

  const reviewedCount = selectedDatasetFindings.filter((finding) =>
    ["confirmed", "corrected", "rejected"].includes(finding.status),
  ).length;
  const highRiskCount = selectedDatasetFindings.filter(
    (finding) => finding.riskScore >= 0.8,
  ).length;
  const reviewProgress = selectedDatasetFindings.length
    ? Math.round((reviewedCount / selectedDatasetFindings.length) * 100)
    : 0;

  const errorDistribution = useMemo(() => {
    const counts = new Map<FindingType, number>();
    selectedDatasetFindings.forEach((finding) =>
      counts.set(finding.type, (counts.get(finding.type) ?? 0) + 1),
    );
    return [...counts.entries()]
      .map(([type, count]) => ({ type, count, label: findingTypeLabels[type] }))
      .sort((first, second) => second.count - first.count)
      .slice(0, 5);
  }, [selectedDatasetFindings]);

  const classDistribution = useMemo(() => {
    const counts = new Map<string, number>();
    selectedDatasetFindings.forEach((finding) => {
      const annotation = state.annotations.find(
        (item) => item.id === finding.annotationId && item.layer === "original",
      );
      const label = annotation?.label ?? "Missing";
      counts.set(label, (counts.get(label) ?? 0) + 1);
    });
    return [...counts.entries()]
      .map(([label, count]) => ({ label, count }))
      .sort((first, second) => second.count - first.count);
  }, [selectedDatasetFindings, state.annotations]);
  const clearFilters = () => {
    setQuery("");
    setStatusFilter("all");
    setSeverityFilter("all");
    setTypeFilter("all");
    setSceneFilter("all");
    setFrameFilter("");
    setClassFilter("all");
    setAnnotatorFilter("all");
    setMinimumRisk(0);
    setSortBy("priority");
    setPage(1);
  };

  const toggleFinding = (findingId: string) => {
    if (!canReview) return;
    setSelectedIds((current) =>
      current.includes(findingId)
        ? current.filter((id) => id !== findingId)
        : [...current, findingId],
    );
  };

  const toggleAllVisible = () => {
    if (!canReview) return;
    if (allVisibleSelected) {
      setSelectedIds((current) =>
        current.filter((id) => !pagedFindings.some((finding) => finding.id === id)),
      );
      return;
    }
    setSelectedIds((current) => [
      ...new Set([...current, ...pagedFindings.map((finding) => finding.id)]),
    ]);
  };

  const applyBulkStatus = (
    status: ReviewStatus,
    action: "start_review" | "confirm" | "skip",
  ) => {
    if (!canReview) return;
    selectedIds.forEach((findingId) =>
      actions.setFindingStatus(findingId, status, action, "Bulk action từ QA Queue"),
    );
    setSelectedIds([]);
  };

  const applyBulkAssignee = () => {
    if (!canReview) return;
    selectedIds.forEach((findingId) => actions.assignFinding(findingId, bulkAssigneeId));
    setSelectedIds([]);
  };

  const isDecisionLocked = selectedFinding
    ? ["confirmed", "corrected", "rejected"].includes(selectedFinding.status)
    : true;

  return (
    <div className="page-container queue-console-page">
      <div className="queue-console-topline">
        <label className="queue-global-search">
          <span aria-hidden="true">⌕</span>
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Tìm kiếm scene, frame, label ID, task ID..."
            aria-label="Tìm kiếm trong QA Queue"
          />
          <kbd>/</kbd>
        </label>
        <div className="queue-context-chips">
          <Badge tone="info">{selectedDataset?.version ?? "dataset version"}</Badge>
          <Badge tone="neutral">{state.activeRole === "reviewer" ? "QA Reviewer" : state.activeRole}</Badge>
          <span className="agent-safety-chip">△ Agent chỉ đề xuất, không tự động sửa nhãn</span>
        </div>
      </div>

      <section className="queue-kpi-grid" aria-label="Tổng quan QA Queue">
        <QueueKpiCard icon="▣" label="Tổng nhãn kiểm tra" value={selectedDataset?.annotationCount ?? 0} detail={`${selectedDataset?.frameCount ?? 0} frame trong dataset`} tone="blue" />
        <QueueKpiCard icon="⚑" label="Nhãn bị gắn cờ" value={selectedDatasetFindings.length} detail={`${visibleFindings.length} case sau bộ lọc`} tone="red" />
        <QueueKpiCard icon="◎" label="Precision / Recall" value={`${state.reportMetrics.precision.toFixed(2)} / ${state.reportMetrics.recall.toFixed(2)}`} detail={`F1 ${state.reportMetrics.f1Score.toFixed(2)}`} tone="purple" />
        <QueueKpiCard icon="✓" label="Đã review" value={reviewedCount} detail={`${reviewProgress}% của hàng đợi`} tone="green" />
        <QueueKpiCard icon="!" label="High-risk cases" value={highRiskCount} detail="Risk score từ 80 trở lên" tone="orange" />
      </section>

      <section className="queue-console-workbench">
        <Card className="queue-console-filter-panel">
          <div className="queue-panel-heading">
            <strong>Bộ lọc</strong>
            <button type="button" onClick={clearFilters}>↻ Đặt lại</button>
          </div>
          <div className="queue-filter-stack">
            <label><span>Dataset</span><select value={state.selectedDatasetId} onChange={(event) => actions.setDataset(event.target.value)}>{state.datasets.map((dataset) => <option key={dataset.id} value={dataset.id}>{dataset.format}</option>)}</select></label>
            <label><span>Scene</span><select value={sceneFilter} onChange={(event) => setSceneFilter(event.target.value)}><option value="all">Tất cả scene</option>{sceneOptions.map((scene) => <option key={scene.id} value={scene.id}>{scene.name}</option>)}</select></label>
            <label><span>Frame</span><input value={frameFilter} onChange={(event) => setFrameFilter(event.target.value)} placeholder="Nhập frame ID" /></label>
            <label><span>Class</span><select value={classFilter} onChange={(event) => setClassFilter(event.target.value)}><option value="all">Tất cả</option>{classOptions.map((label) => <option key={label} value={label}>{label}</option>)}</select></label>
            <label><span>Loại lỗi</span><select value={typeFilter} onChange={(event) => setTypeFilter(event.target.value as FindingType | "all")}><option value="all">Tất cả</option>{Object.entries(findingTypeLabels).map(([type, label]) => <option key={type} value={type}>{label}</option>)}</select></label>
            <label><span>Severity</span><select value={severityFilter} onChange={(event) => setSeverityFilter(event.target.value as Severity | "all")}><option value="all">Tất cả</option><option value="critical">Critical</option><option value="high">High</option><option value="medium">Warning</option><option value="low">Low</option></select></label>
            <label><span>Annotator</span><select value={annotatorFilter} onChange={(event) => setAnnotatorFilter(event.target.value)}><option value="all">Tất cả</option>{state.users.filter((user) => user.role !== "admin").map((user) => <option key={user.id} value={user.id}>{user.name}</option>)}</select></label>
            <label><span>Trạng thái review</span><select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as ReviewStatus | "all")}><option value="all">Tất cả</option>{reviewStatuses.map((status) => <option key={status} value={status}>{statusLabels[status]}</option>)}</select></label>
            <label className="queue-risk-filter"><span>Risk score <strong>{minimumRisk}</strong></span><input type="range" min="0" max="100" value={minimumRisk} onChange={(event) => setMinimumRisk(Number(event.target.value))} /></label>
            <label><span>Sắp xếp theo độ ưu tiên</span><select value={sortBy} onChange={(event) => setSortBy(event.target.value as QueueSortKey)}><option value="priority">Cao → Thấp</option><option value="risk">Risk giảm dần</option><option value="newest">Mới nhất</option></select></label>
          </div>
        </Card>

        <Card className="queue-console-viewer-card">
          <MockQueueComparisonViewer state={state} finding={selectedFinding} />
        </Card>

        <Card className="queue-console-detail-panel">
          {selectedFinding ? (
            <>
              <div className="queue-panel-heading queue-detail-heading">
                <div><strong>Chi tiết case</strong><small>{selectedFinding.id}</small></div>
                {onOpenFinding ? <button type="button" onClick={() => onOpenFinding(selectedFinding.id)}>Mở đầy đủ ↗</button> : null}
              </div>
              <dl className="queue-case-metadata">
                <div><dt>Annotation</dt><dd>{selectedFinding.annotationId ?? "new"}</dd></div>
                <div><dt>Scene</dt><dd>{selectedScene?.name ?? selectedFinding.sceneId}</dd></div>
                <div><dt>Frame</dt><dd>{selectedFrame?.frameNumber ?? "—"}</dd></div>
                <div><dt>Class</dt><dd>{selectedAnnotation?.label ?? "Missing object"}</dd></div>
                <div><dt>Error type</dt><dd><Badge tone={selectedFinding.severity}>{findingTypeLabels[selectedFinding.type]}</Badge></dd></div>
                <div><dt>Risk score</dt><dd><Badge tone={selectedFinding.severity}>{Math.round(selectedFinding.riskScore * 100)} / 100</Badge></dd></div>
                <div><dt>Trạng thái</dt><dd><StatusBadge status={selectedFinding.status} /></dd></div>
                <div><dt>Editor</dt><dd>Built-in 2D Editor</dd></div>
              </dl>

              <div className="queue-detail-section">
                <strong>Bằng chứng</strong>
                <ul>{selectedEvidence.map((evidence) => <li key={evidence.id}>{evidence.description}</li>)}</ul>
              </div>

              <div className="queue-agent-explanation">
                <div><span>▣</span><strong>Giải thích của Agent</strong></div>
                <p>{selectedFinding.explanation}</p>
              </div>

              <div className="queue-detail-section queue-recommendation-section">
                <strong>Đề xuất xử lý</strong>
                <p>{selectedFinding.recommendation}</p>
              </div>

              {canReview ? (
                <div className="queue-case-actions">
                  <Button variant="primary" disabled={isDecisionLocked} onClick={() => actions.setFindingStatus(selectedFinding.id, "confirmed", "confirm", "Xác nhận nhanh từ QA Queue")}>✓ Xác nhận</Button>
                  <Button variant="secondary" onClick={onOpenEditor}>Edit Label</Button>
                  <Button variant="danger" disabled={isDecisionLocked} onClick={() => actions.setFindingStatus(selectedFinding.id, "rejected", "reject_finding", "Bác bỏ nhanh từ QA Queue")}>× Bác bỏ</Button>
                </div>
              ) : (
                <div className="queue-permission-note">Admin có thể xem evidence nhưng không được quyết định hoặc chỉnh annotation.</div>
              )}
            </>
          ) : (
            <div className="queue-detail-empty">Không có case phù hợp với bộ lọc hiện tại.</div>
          )}
        </Card>
      </section>

      <section className="queue-console-bottom-grid">
        <Card className="queue-console-table-card">
          <div className="queue-table-titlebar">
            <div><strong>Danh sách nhãn nghi ngờ</strong><Badge tone="neutral">{visibleFindings.length} items</Badge></div>
            <button type="button" onClick={clearFilters} aria-label="Làm mới danh sách">↻</button>
          </div>

          {selectedIds.length > 0 ? (
            <div className="queue-inline-bulk">
              <strong>{selectedIds.length} case</strong>
              <Button size="sm" variant="secondary" onClick={() => applyBulkStatus("in_review", "start_review")}>Đưa vào review</Button>
              <Button size="sm" variant="secondary" onClick={() => applyBulkStatus("confirmed", "confirm")}>Xác nhận</Button>
              <Button size="sm" variant="ghost" onClick={() => applyBulkStatus("skipped", "skip")}>Tạm hoãn</Button>
              <select value={bulkAssigneeId} onChange={(event) => setBulkAssigneeId(event.target.value)}>{state.users.filter((user) => user.role !== "admin").map((user) => <option key={user.id} value={user.id}>{user.name}</option>)}</select>
              <Button size="sm" variant="secondary" onClick={applyBulkAssignee}>Gán</Button>
              <Button size="sm" variant="ghost" onClick={() => setSelectedIds([])}>Bỏ chọn</Button>
            </div>
          ) : null}

          <div className="queue-console-table-wrap">
            <table className="queue-console-table">
              <thead><tr><th><input type="checkbox" disabled={!canReview} checked={allVisibleSelected} onChange={toggleAllVisible} aria-label="Chọn tất cả case" /></th><th>Frame</th><th>Object / Class</th><th>Issue type</th><th>Severity</th><th>Confidence</th><th>Source</th><th>Status</th><th>Action</th></tr></thead>
              <tbody>
                {pagedFindings.map((finding) => {
                  const scene = state.scenes.find((item) => item.id === finding.sceneId);
                  const frame = state.frames.find((item) => item.id === finding.frameId);
                  const annotation = state.annotations.find((item) => item.id === finding.annotationId && item.layer === "original");
                  const prediction = state.predictions.find((item) => item.frameId === finding.frameId && (!finding.trackId || item.trackId === finding.trackId));
                  return (
                    <tr className={selectedFindingId === finding.id ? "is-selected" : ""} key={finding.id} onClick={() => setSelectedFindingId(finding.id)}>
                      <td><input type="checkbox" disabled={!canReview} checked={selectedIds.includes(finding.id)} onClick={(event) => event.stopPropagation()} onChange={() => toggleFinding(finding.id)} aria-label={`Chọn ${finding.id}`} /></td>
                      <td><button className="queue-frame-cell" type="button" onClick={() => setSelectedFindingId(finding.id)}><img src={frame?.thumbnailUrl} alt="" /><span><strong>Frame {frame?.frameNumber ?? "—"}</strong><small>{scene?.name ?? "—"}</small></span></button></td>
                      <td><span className="queue-object-cell"><strong>{annotation?.label ?? "Missing"}</strong><small>{finding.trackId ?? finding.id}</small></span></td>
                      <td>{findingTypeLabels[finding.type]}</td><td><Badge tone={finding.severity}>{finding.severity}</Badge></td>
                      <td><span className="queue-confidence"><strong>{Math.round((prediction?.confidence ?? finding.riskScore) * 100)}%</strong><i><span style={{ width: `${(prediction?.confidence ?? finding.riskScore) * 100}%` }} /></i></span></td>
                      <td><span className="queue-source-cell">{prediction ? "Model + Rule" : "QA Rule"}</span></td><td><StatusBadge status={finding.status} /></td>
                      <td><button className="queue-row-action" type="button" onClick={(event) => { event.stopPropagation(); onOpenFinding?.(finding.id); }}>Review</button></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {visibleFindings.length === 0 ? <div className="queue-console-empty"><strong>Không có case phù hợp</strong><span>Hãy giảm điều kiện lọc hoặc chọn dataset khác.</span><Button size="sm" variant="secondary" onClick={clearFilters}>Đặt lại bộ lọc</Button></div> : null}
          </div>
          <div className="queue-table-pagination">
            <span>
              Hiển thị {visibleFindings.length === 0 ? 0 : (page - 1) * PAGE_SIZE + 1} – {Math.min(page * PAGE_SIZE, visibleFindings.length)} trong {visibleFindings.length}
            </span>
            <label>
              <select value={PAGE_SIZE} disabled aria-label="Số case mỗi trang">
                <option value={PAGE_SIZE}>10 / trang</option>
              </select>
            </label>
            <div>
              <button type="button" disabled={page === 1} onClick={() => setPage((current) => Math.max(1, current - 1))}>‹</button>
              {Array.from({ length: pageCount }, (_, index) => index + 1).map((pageNumber) => (
                <button key={pageNumber} type="button" className={pageNumber === page ? "is-current" : ""} onClick={() => setPage(pageNumber)}>{pageNumber}</button>
              ))}
              <button type="button" disabled={page === pageCount} onClick={() => setPage((current) => Math.min(pageCount, current + 1))}>›</button>
            </div>
          </div>
        </Card>

        <QueueAnalytics
          errorDistribution={errorDistribution}
          classDistribution={classDistribution}
          totalCount={selectedDatasetFindings.length}
          reviewedCount={reviewedCount}
          reviewProgress={reviewProgress}
        />
      </section>
    </div>
  );
}
