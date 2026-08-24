import { useEffect, useState } from "react";
import { Badge, Button, Card, StatusBadge } from "./ui";
import type { Finding, MockState, ReviewStatus } from "../domain/types";
import { canSubmitAnnotatorFeedback } from "../domain/permissions";
import { useMockData } from "../state/MockDataProvider";

const statusDescriptions: Record<ReviewStatus, string> = {
  unreviewed: "Agent đã gắn cờ, chờ quyết định của reviewer.",
  in_review: "Reviewer đang kiểm tra evidence và annotation revision hiện tại.",
  confirmed: "Reviewer xác nhận annotation hiện tại là đúng.",
  corrected: "Thay đổi đã được lưu bởi 2D Editor và ghi nhận vào lịch sử.",
  rejected: "Finding được xác định là false positive.",
  skipped: "Case được tạm hoãn và cần xem lại sau.",
};

export function ReviewActions({
  state,
  finding,
}: {
  state: MockState;
  finding: Finding;
}) {
  const { actions } = useMockData();
  const [reason, setReason] = useState("");
  const [assigneeId, setAssigneeId] = useState("user-annotator");
  const [showAssign, setShowAssign] = useState(false);
  const [pendingAction, setPendingAction] = useState<PendingAction | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const proposal = state.annotations.find(
    (annotation) =>
      annotation.layer === "proposed" &&
      ((finding.annotationId && annotation.sourceAnnotationId === finding.annotationId) ||
        annotation.sourceFindingId === finding.id),
  );
  const actionDisabled = ["corrected", "confirmed", "rejected"].includes(finding.status);
  const isReviewer = state.activeRole === "reviewer";

  useEffect(() => {
    if (!toast) {
      return;
    }
    const timeoutId = window.setTimeout(() => setToast(null), 3200);
    return () => window.clearTimeout(timeoutId);
  }, [toast]);

  if (!isReviewer) {
    const isAnnotator = state.activeRole === "annotator";
    const canSubmitFeedback = canSubmitAnnotatorFeedback(
      finding,
      state.activeRole,
      state.activeUserId,
    );
    return (
      <Card className="review-actions-card role-guard-card">
        <div className="review-actions-heading">
          <div>
            <span className="eyebrow">FE-34 · Role-based access</span>
            <h2>Quyền thao tác của {state.activeRole}</h2>
          </div>
          <Badge tone="neutral">Review decision bị khóa</Badge>
        </div>
        <div className="role-guard-banner">
          <strong>
            {isAnnotator && canSubmitFeedback
              ? "Annotator nhận task và chỉnh annotation trong 2D Editor."
              : isAnnotator
                ? "Case này chưa được giao cho annotator hiện tại."
              : "Admin quản lý QA run, rule và model configuration."}
          </strong>
          <p>
            {isAnnotator && canSubmitFeedback
              ? "Approve/reject thuộc reviewer; feedback và trạng thái task sẽ đi qua backend khi tích hợp."
              : isAnnotator
                ? "Frontend khóa deep-link và feedback; reviewer cần assign case trước khi annotator xử lý."
              : "Admin không đưa ra human review decision trên QA case để giữ phân tách trách nhiệm."}
          </p>
          {isAnnotator && canSubmitFeedback ? (
            <>
              <label className="review-reason-field annotator-feedback-field">
                <span>Phản hồi cho reviewer</span>
                <textarea
                  value={reason}
                  onChange={(event) => setReason(event.target.value)}
                  placeholder="Mô tả thay đổi đã thực hiện hoặc vấn đề cần reviewer hỗ trợ..."
                  rows={3}
                />
              </label>
              <div className="role-guard-actions">
                <Button
                  variant="primary"
                  disabled={!reason.trim()}
                  onClick={() => {
                    actions.submitFeedback(finding.id, reason);
                    setReason("");
                    setToast("Đã gửi phản hồi mock cho reviewer");
                  }}
                >
                  Gửi phản hồi
                </Button>
              </div>
            </>
          ) : null}
        </div>
        {toast ? (
          <div className="review-toast" role="status">
            <span>✓</span>
            {toast}
            <button type="button" onClick={() => setToast(null)} aria-label="Đóng thông báo">×</button>
          </div>
        ) : null}
      </Card>
    );
  }

  const requestStatusAction = (
    status: ReviewStatus,
    action: "start_review" | "confirm" | "reject_finding" | "skip",
    needsReason = false,
  ) => {
    if (needsReason && !reason.trim()) {
      setToast("Vui lòng nhập lý do trước khi thực hiện quyết định này");
      return;
    }
    setPendingAction({
      kind: "status",
      status,
      action,
      reason: reason.trim() || undefined,
      label:
        status === "confirmed"
          ? "Xác nhận annotation hiện tại"
          : status === "rejected"
            ? "Bác bỏ finding"
            : status === "skipped"
              ? "Tạm hoãn case"
              : "Bắt đầu review",
    });
  };

  const confirmPendingAction = () => {
    if (!pendingAction) {
      return;
    }

    if (pendingAction.kind === "status") {
      actions.setFindingStatus(
        finding.id,
        pendingAction.status,
        pendingAction.action,
        pendingAction.reason,
      );
      setToast(`Đã cập nhật trạng thái: ${pendingAction.label}`);
    } else {
      actions.approveFinding(finding.id, reason.trim() || undefined);
      setToast("Đã phê duyệt proposal trong lịch sử review");
    }
    setReason("");
    setPendingAction(null);
  };

  return (
    <Card className="review-actions-card">
      <div className="review-actions-heading">
        <div>
          <span className="eyebrow">Human decision</span>
          <h2>Review decision</h2>
        </div>
        <Badge tone="info">Reviewer only</Badge>
      </div>

      <div className="current-status-banner">
        <StatusBadge status={finding.status} />
        <span>{statusDescriptions[finding.status]}</span>
      </div>

      <label className="review-reason-field">
        <span>Decision note</span>
        <textarea
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          placeholder="Ghi evidence hoặc lý do cho quyết định audit..."
          rows={3}
        />
      </label>

      <div className="review-action-grid">
        {finding.status === "unreviewed" || finding.status === "skipped" ? (
          <Button
            variant="secondary"
            onClick={() => requestStatusAction("in_review", "start_review")}
          >
            Send to review
          </Button>
        ) : null}
        <Button
          variant="primary"
          disabled={actionDisabled}
          onClick={() => requestStatusAction("confirmed", "confirm")}
        >
          Accept annotation
        </Button>
        <Button
          variant="danger"
          disabled={actionDisabled}
          onClick={() => requestStatusAction("rejected", "reject_finding", true)}
        >
          Reject finding
        </Button>
        <Button
          variant="ghost"
          disabled={actionDisabled}
          onClick={() => requestStatusAction("skipped", "skip", true)}
        >
          Defer case
        </Button>
        {proposal ? (
          <Button
            variant="primary"
            disabled={actionDisabled}
            onClick={() =>
              setPendingAction({ kind: "approve", label: "Phê duyệt thay đổi" })
            }
          >
            Phê duyệt thay đổi
          </Button>
        ) : null}
      </div>

      <div className="assign-reviewer-section">
        <button
          className="assign-toggle"
          type="button"
          onClick={() => setShowAssign((visible) => !visible)}
        >
          <span>Chuyển case cho annotator/reviewer</span>
          <span>{showAssign ? "⌃" : "⌄"}</span>
        </button>
        {showAssign ? (
          <div className="assign-controls">
            <select value={assigneeId} onChange={(event) => setAssigneeId(event.target.value)}>
              {state.users
                .filter((user) => user.role !== "admin")
                .map((user) => (
                  <option key={user.id} value={user.id}>{`${user.name} · ${user.role}`}</option>
                ))}
            </select>
            <Button
              size="sm"
              variant="secondary"
              onClick={() => {
                actions.assignFinding(finding.id, assigneeId);
                setShowAssign(false);
                setToast("Đã chuyển case cho người được chọn");
              }}
            >
              Gán case
            </Button>
          </div>
        ) : null}
      </div>

      <p className="review-action-footnote">
        2D Editor lưu annotation trực tiếp thành revision; quyết định review được ghi riêng trong audit log.
      </p>

      {pendingAction ? (
        <div className="review-modal-backdrop" role="presentation">
          <div
            className="review-confirm-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="review-confirm-title"
          >
            <span className="eyebrow">Confirm human decision</span>
            <h3 id="review-confirm-title">{pendingAction.label}?</h3>
            <p>
              {pendingAction.kind === "approve"
                ? "Proposal sẽ chuyển sang trạng thái đã duyệt trong lịch sử review."
                : "Thao tác cập nhật review state và tạo một decision trong mock audit log."}
            </p>
            <div className="review-modal-actions">
              <Button variant="ghost" onClick={() => setPendingAction(null)}>Hủy</Button>
              <Button variant="primary" onClick={confirmPendingAction}>Xác nhận thao tác</Button>
            </div>
          </div>
        </div>
      ) : null}

      {toast ? (
        <div className="review-toast" role="status">
          <span>✓</span>
          {toast}
          <button type="button" onClick={() => setToast(null)} aria-label="Đóng thông báo">×</button>
        </div>
      ) : null}
    </Card>
  );
}

type PendingAction =
  | {
      kind: "status";
      status: ReviewStatus;
      action: "start_review" | "confirm" | "reject_finding" | "skip";
      reason?: string;
      label: string;
    }
  | { kind: "approve"; label: string };
