import type { AnnotationRecord, Finding, MockState, PredictionRecord } from "../domain/types";
import { Badge, Card } from "./ui";

type ComparableAnnotation = Pick<
  AnnotationRecord | PredictionRecord,
  "label" | "trackId" | "bbox"
>;

function annotationSummary(annotation?: ComparableAnnotation): string {
  if (!annotation) {
    return "Không có object";
  }

  const box = annotation.bbox;
  return `${annotation.trackId ?? "no-id"} · ${box.x},${box.y},${box.width}×${box.height}`;
}

export function AnnotationEditPanel({
  state,
  finding,
}: {
  state: MockState;
  finding: Finding;
}) {
  const original = state.annotations.find(
    (annotation) => annotation.id === finding.annotationId && annotation.layer === "original",
  );
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
  const prediction = state.predictions.find(
    (item) => item.frameId === finding.frameId && item.trackId === finding.trackId,
  );
  const candidate = proposal ?? prediction;

  const layerSummary = [
    {
      label: "Original",
      layer: "original",
      version: original?.version,
      detail: "Nhãn gốc trước khi chỉnh sửa",
    },
    {
      label: "Agent proposal",
      layer: "proposed",
      version: proposal?.version,
      detail: proposal ? "Gợi ý, chưa phải Ground Truth" : "Chưa có proposal",
    },
    {
      label: "Approved snapshot",
      layer: "approved",
      version: approved?.version,
      detail: approved ? "Đã duyệt và lưu trong lịch sử" : "Chưa phê duyệt",
    },
  ];

  return (
    <Card className="annotation-edit-card proposal-companion-card">
      <div className="annotation-edit-heading">
        <div>
          <span className="eyebrow">Annotation comparison</span>
          <h2>So sánh annotation chỉ đọc</h2>
        </div>
        <Badge tone="info">Built-in 2D Editor</Badge>
      </div>

      <div className="annotation-layer-lineage">
        {layerSummary.map((item) => (
          <div className={`layer-version layer-version-${item.layer}`} key={item.layer}>
            <div className="layer-version-top">
              <span>{item.label}</span>
              <strong>{item.version ? `v${item.version}` : "—"}</strong>
            </div>
            <small>{item.detail}</small>
          </div>
        ))}
      </div>

      <div className="annotation-preview-card proposal-diff-card">
        <div className="annotation-preview-heading">
          <span className="eyebrow">Before / suggested</span>
          <span>Evidence hỗ trợ review, không ghi Ground Truth</span>
        </div>
        <div className="annotation-preview-grid">
          <div className="annotation-preview-pane">
            <span>Before · original revision</span>
            <strong>{original?.label ?? "Missing object"}</strong>
            <small>{annotationSummary(original)}</small>
          </div>
          <div className="annotation-preview-pane annotation-preview-after">
            <span>Suggested · {proposal ? "agent proposal" : "model reference"}</span>
            <strong>{candidate?.label ?? "Chưa có gợi ý"}</strong>
            <small>{annotationSummary(candidate)}</small>
          </div>
        </div>
      </div>

      <div className="proposal-feedback-callout">
        <div>
          <span className="eyebrow">Boundary rõ ràng</span>
          <strong>Chỉnh bbox, class, track và attributes trong 2D Editor</strong>
          <p>
            Mở 2D Editor từ case để chỉnh trực tiếp. Mỗi lần lưu tạo một revision có thể khôi phục và audit.
          </p>
        </div>
      </div>
    </Card>
  );
}
