import { useMemo, useState, type CSSProperties } from "react";
import { Badge, Button } from "./ui";
import type { AnnotationLayer, Finding, MockState } from "../domain/types";

interface FrameViewerProps {
  state: MockState;
  finding: Finding;
  frameId: string;
}

const layerLabels: Record<AnnotationLayer | "prediction", string> = {
  original: "Nhãn gốc",
  prediction: "Prediction",
  proposed: "Đề xuất",
  approved: "Đã duyệt",
};

function boxStyle(
  x: number,
  y: number,
  width: number,
  height: number,
  frameWidth: number,
  frameHeight: number,
): CSSProperties {
  return {
    left: `${(x / frameWidth) * 100}%`,
    top: `${(y / frameHeight) * 100}%`,
    width: `${(width / frameWidth) * 100}%`,
    height: `${(height / frameHeight) * 100}%`,
  };
}

export function FrameViewer({ state, finding, frameId }: FrameViewerProps) {
  const [showOriginal, setShowOriginal] = useState(true);
  const [showPrediction, setShowPrediction] = useState(true);
  const [showProposed, setShowProposed] = useState(true);
  const [showApproved, setShowApproved] = useState(true);
  const [zoom, setZoom] = useState(100);
  const frame = state.frames.find((item) => item.id === frameId);

  const annotations = useMemo(
    () => state.annotations.filter((annotation) => annotation.frameId === frameId),
    [frameId, state.annotations],
  );
  const predictions = useMemo(
    () => state.predictions.filter((prediction) => prediction.frameId === frameId),
    [frameId, state.predictions],
  );

  if (!frame) {
    return (
      <div className="frame-viewer-empty">
        <strong>Không tìm thấy frame</strong>
        <span>{frameId}</span>
      </div>
    );
  }

  const annotationVisible = (layer: AnnotationLayer) =>
    (layer === "original" && showOriginal) ||
    (layer === "proposed" && showProposed) ||
    (layer === "approved" && showApproved);

  return (
    <div className="frame-viewer">
      <div className="frame-viewer-toolbar">
        <div className="frame-viewer-toolbar-left">
          <span className="eyebrow">Frame viewer</span>
          <Badge tone="info">Frame {frame.frameNumber}</Badge>
          {frame.anonymized ? <Badge tone="success">Anonymized</Badge> : null}
        </div>
        <div className="frame-viewer-toolbar-right">
          <Button size="sm" variant="ghost" onClick={() => setZoom((current) => Math.max(75, current - 25))}>−</Button>
          <span className="zoom-value">{zoom}%</span>
          <Button size="sm" variant="ghost" onClick={() => setZoom((current) => Math.min(175, current + 25))}>+</Button>
          <Button size="sm" variant="ghost" onClick={() => setZoom(100)}>Reset</Button>
        </div>
      </div>

      <div className="frame-stage-shell">
        <div
          className="frame-stage"
          style={{
            aspectRatio: `${frame.width} / ${frame.height}`,
            transform: `scale(${zoom / 100})`,
          }}
        >
          <img src={frame.thumbnailUrl} alt={`Mock frame ${frame.frameNumber}`} />
          <div className="frame-overlay-layer">
            {annotations.filter((annotation) => annotationVisible(annotation.layer) && !annotation.attributes.deleted).map((annotation) => (
              <div
                className={`annotation-overlay overlay-${annotation.layer} ${annotation.id === finding.annotationId ? "is-flagged" : ""}`}
                key={annotation.id}
                style={boxStyle(annotation.bbox.x, annotation.bbox.y, annotation.bbox.width, annotation.bbox.height, frame.width, frame.height)}
              >
                <span>{annotation.label} · {annotation.trackId ?? "no-id"}</span>
              </div>
            ))}
            {showPrediction ? predictions.map((prediction) => (
              <div
                className={`annotation-overlay overlay-prediction ${prediction.trackId === finding.trackId ? "is-flagged" : ""}`}
                key={prediction.id}
                style={boxStyle(prediction.bbox.x, prediction.bbox.y, prediction.bbox.width, prediction.bbox.height, frame.width, frame.height)}
              >
                <span>{prediction.label} · {Math.round(prediction.confidence * 100)}%</span>
              </div>
            )) : null}
          </div>
        </div>
      </div>

      <div className="frame-viewer-legend">
        <button className={`legend-toggle toggle-original ${showOriginal ? "is-on" : ""}`} type="button" onClick={() => setShowOriginal((visible) => !visible)} aria-pressed={showOriginal}>
          <span className="legend-swatch" />{layerLabels.original}
        </button>
        <button className={`legend-toggle toggle-prediction ${showPrediction ? "is-on" : ""}`} type="button" onClick={() => setShowPrediction((visible) => !visible)} aria-pressed={showPrediction}>
          <span className="legend-swatch" />{layerLabels.prediction}
        </button>
        <button className={`legend-toggle toggle-proposed ${showProposed ? "is-on" : ""}`} type="button" onClick={() => setShowProposed((visible) => !visible)} aria-pressed={showProposed}>
          <span className="legend-swatch" />{layerLabels.proposed}
        </button>
        <button className={`legend-toggle toggle-approved ${showApproved ? "is-on" : ""}`} type="button" onClick={() => setShowApproved((visible) => !visible)} aria-pressed={showApproved}>
          <span className="legend-swatch" />{layerLabels.approved}
        </button>
      </div>
    </div>
  );
}
