import { useMemo } from "react";
import { Badge, Card, StatusBadge } from "./ui";
import type { Finding, MockState, ReviewAction } from "../domain/types";

const actionLabels: Record<ReviewAction, string> = {
  start_review: "Bắt đầu review",
  confirm: "Xác nhận nhãn",
  approve_correction: "Phê duyệt chỉnh sửa",
  edit_annotation: "Tạo/cập nhật proposal",
  annotator_feedback: "Phản hồi từ annotator",
  reject_finding: "Bác bỏ cảnh báo",
  skip: "Bỏ qua case",
  assign: "Gán người xử lý",
};

export function ReviewHistoryPanel({
  state,
  finding,
}: {
  state: MockState;
  finding: Finding;
}) {
  const decisions = useMemo(
    () => state.reviewDecisions.filter((decision) => decision.findingId === finding.id).slice().reverse(),
    [finding.id, state.reviewDecisions],
  );
  const original = state.annotations.find((annotation) => annotation.id === finding.annotationId && annotation.layer === "original");
  const proposal = state.annotations.find(
    (annotation) =>
      annotation.layer === "proposed" &&
      ((finding.annotationId && annotation.sourceAnnotationId === finding.annotationId) ||
        annotation.sourceFindingId === finding.id),
  );
  const approved = state.annotations.find(
    (annotation) =>
      annotation.layer === "approved" &&
      ((finding.annotationId && annotation.sourceAnnotationId === finding.annotationId) ||
        annotation.sourceFindingId === finding.id),
  );

  return (
    <Card className="review-history-card">
      <div className="review-history-heading">
        <div>
          <span className="eyebrow">FE-18 · Audit trail</span>
          <h2>History & version lineage</h2>
        </div>
        <Badge tone="neutral">{decisions.length} decisions</Badge>
      </div>

      <div className="history-version-strip">
        <div><span>Original</span><strong>{original ? `v${original.version}` : "—"}</strong><small>Immutable</small></div>
        <span className="version-arrow">→</span>
        <div><span>Proposed</span><strong>{proposal ? `v${proposal.version}` : "—"}</strong><small>{proposal ? proposal.updatedBy : "Not created"}</small></div>
        <span className="version-arrow">→</span>
        <div><span>Approved</span><strong>{approved ? `v${approved.version}` : "—"}</strong><small>{approved ? approved.updatedBy : "Not approved"}</small></div>
      </div>

      {decisions.length > 0 ? (
        <div className="audit-list">
          {decisions.map((decision) => {
            const user = state.users.find((item) => item.id === decision.userId);
            return (
              <div className="audit-row" key={decision.id}>
                <div className="audit-marker" />
                <div className="audit-copy">
                  <div className="audit-title"><strong>{actionLabels[decision.action]}</strong><StatusBadge status={decision.toStatus} /></div>
                  <p>{decision.changeSummary ?? decision.reason ?? "Không có ghi chú"}</p>
                  {decision.changeSummary && decision.reason ? <small className="audit-reason">Ghi chú: {decision.reason}</small> : null}
                  <small>{user?.name ?? decision.userId} · {new Date(decision.timestamp).toLocaleString("vi-VN")}</small>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="audit-empty">Chưa có quyết định review nào. Các thao tác của reviewer sẽ xuất hiện ở đây.</div>
      )}
    </Card>
  );
}
