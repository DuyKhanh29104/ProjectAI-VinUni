import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
} from "react";
import type {
  QaCaseDto,
  QaPredictionEvidenceDto,
  RealDatasetLabelDto,
} from "../../../api/types";
import { useAuthenticatedAssetUrl } from "../../../components/AuthenticatedImage";
import { Badge, Button } from "../../../components/ui";
import {
  apiBoxIntersectsImage,
  boxIntersectsImage,
} from "../../../utils/realDataset";

type ComparisonMode = "gt" | "prediction" | "both";

function boxStyle(
  bbox: { x: number; y: number; width: number; height: number },
  frameWidth: number,
  frameHeight: number,
): CSSProperties {
  return {
    left: `${(bbox.x / frameWidth) * 100}%`,
    top: `${(bbox.y / frameHeight) * 100}%`,
    width: `${(bbox.width / frameWidth) * 100}%`,
    height: `${(bbox.height / frameHeight) * 100}%`,
  };
}

const predictionBox = (item: QaPredictionEvidenceDto) => {
  const [x, y, width, height] = item.bbox;
  return { x, y, width, height };
};
const groundTruthBox = (item: RealDatasetLabelDto) => ({
  x: item.bbox.x1,
  y: item.bbox.y1,
  width: item.bbox.x2 - item.bbox.x1,
  height: item.bbox.y2 - item.bbox.y1,
});

export function ApiQueueComparisonViewer({ qaCase }: { qaCase?: QaCaseDto }) {
  const [mode, setMode] = useState<ComparisonMode>("both");
  const [zoom, setZoom] = useState(100);
  const [stageSize, setStageSize] = useState({ width: 0, height: 0 });
  const [frameSize, setFrameSize] = useState({ width: 1280, height: 720 });
  const [frameError, setFrameError] = useState("");
  const stageRef = useRef<HTMLDivElement>(null);
  const frameAsset = useAuthenticatedAssetUrl(qaCase?.evidence.imageUrl);

  useEffect(() => {
    setZoom(100);
    setFrameError("");
  }, [qaCase?.id]);
  useEffect(() => {
    const stage = stageRef.current;
    if (!stage) return;
    const resize = () =>
      setStageSize({ width: stage.clientWidth, height: stage.clientHeight });
    resize();
    const observer =
      typeof ResizeObserver === "undefined" ? null : new ResizeObserver(resize);
    observer?.observe(stage);
    window.addEventListener("resize", resize);
    return () => {
      observer?.disconnect();
      window.removeEventListener("resize", resize);
    };
  }, [qaCase?.id]);

  const labels = useMemo(
    () => qaCase?.evidence.groundTruthLabels ?? [],
    [qaCase],
  );
  const predictions = useMemo(
    () => qaCase?.evidence.observedPredictions ?? [],
    [qaCase],
  );
  if (!qaCase)
    return (
      <div className="queue-comparison-empty">
        <span>◇</span>
        <strong>Chọn một case để mở viewer</strong>
        <small>Viewer dùng để so sánh nhãn hiện tại và prediction.</small>
      </div>
    );

  const sourceWidth = qaCase.evidence.imageWidth ?? frameSize.width;
  const sourceHeight = qaCase.evidence.imageHeight ?? frameSize.height;
  const displayedLabels = labels.filter((label) =>
    apiBoxIntersectsImage(label.bbox, sourceWidth, sourceHeight),
  );
  const displayedPredictions = predictions.filter((prediction) =>
    boxIntersectsImage(predictionBox(prediction), sourceWidth, sourceHeight),
  );
  const availableWidth = Math.max(stageSize.width - 24, 1);
  const availableHeight = Math.max(stageSize.height - 24, 1);
  const fitScale =
    stageSize.width && stageSize.height
      ? Math.min(availableWidth / sourceWidth, availableHeight / sourceHeight)
      : 1;
  const scale = (fitScale * zoom) / 100;
  const canvasWidth = sourceWidth * scale;
  const canvasHeight = sourceHeight * scale;
  return (
    <div className="queue-comparison-viewer">
      <div className="queue-viewer-heading">
        <div>
          <strong>Khung so sánh nhãn</strong>
          <span>Annotation revision hiện tại · viewer chỉ đọc</span>
        </div>
        <Badge tone="info">Frame {qaCase.frameIndex}</Badge>
      </div>
      <div className="queue-viewer-toolbar">
        <Button size="sm" variant="ghost" onClick={() => setZoom(100)}>
          Vừa khung
        </Button>
        <div className="viewer-compare-controls">
          <span>GT / Prediction</span>
          <div
            className="compare-segmented"
            role="group"
            aria-label="Chế độ so sánh"
          >
            <button
              className={mode === "gt" ? "is-active" : ""}
              type="button"
              onClick={() => setMode("gt")}
            >
              GT
            </button>
            <button
              className={mode === "prediction" ? "is-active" : ""}
              type="button"
              onClick={() => setMode("prediction")}
            >
              Prediction
            </button>
            <button
              className={mode === "both" ? "is-active" : ""}
              type="button"
              onClick={() => setMode("both")}
            >
              Cả hai
            </button>
          </div>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => setZoom((value) => Math.max(75, value - 25))}
          >
            −
          </Button>
          <span className="viewer-zoom-value">{zoom}%</span>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => setZoom((value) => Math.min(175, value + 25))}
          >
            +
          </Button>
        </div>
      </div>
      <div ref={stageRef} className="queue-viewer-stage tool-select">
        <div
          className="queue-viewer-stage-content"
          style={{
            width: Math.max(availableWidth, canvasWidth),
            height: Math.max(availableHeight, canvasHeight),
          }}
        >
          <div
            className="queue-viewer-canvas is-auto-fit"
            style={{ width: canvasWidth, height: canvasHeight }}
          >
            {frameAsset.source ? (
              <img
                src={frameAsset.source}
                alt={`Frame ${qaCase.frameIndex}`}
                onLoad={(event) => {
                  setFrameError("");
                  setFrameSize({
                    width: event.currentTarget.naturalWidth,
                    height: event.currentTarget.naturalHeight,
                  });
                }}
                onError={() => setFrameError("Không thể tải ảnh nguồn.")}
              />
            ) : frameAsset.error ? (
              <div className="queue-comparison-empty">
                <strong>{frameAsset.error}</strong>
              </div>
            ) : (
              <div className="queue-comparison-empty">
                <strong>{qaCase.evidence.imageUrl ? "Đang tải ảnh…" : "Case không có ảnh nguồn"}</strong>
              </div>
            )}
            <div className="queue-viewer-overlays">
              {mode !== "prediction"
                ? displayedLabels.map((label) => (
                    <div
                      className={`queue-overlay queue-overlay-gt ${label.id === qaCase.targetTrackId ? "is-selected" : ""}`}
                      key={label.id}
                      style={boxStyle(
                        groundTruthBox(label),
                        sourceWidth,
                        sourceHeight,
                      )}
                    >
                      <span>{label.className} · GT</span>
                    </div>
                  ))
                : null}
              {mode !== "gt"
                ? displayedPredictions.map((prediction) => (
                    <div
                      className={`queue-overlay queue-overlay-prediction ${prediction.trackId === qaCase.targetTrackId ? "is-selected" : ""}`}
                      key={prediction.id}
                      style={boxStyle(
                        predictionBox(prediction),
                        sourceWidth,
                        sourceHeight,
                      )}
                    >
                      <span>
                        {prediction.label} ·{" "}
                        {Math.round(prediction.confidence * 100)}%
                      </span>
                    </div>
                  ))
                : null}
            </div>
          </div>
        </div>
        {frameError ? (
          <div className="api-viewer-state is-error">{frameError}</div>
        ) : null}
        <div className="queue-viewer-legend">
          <span>
            <i className="legend-box-gt" />
            Nhãn hiện tại
          </span>
          <span>
            <i className="legend-box-prediction" />
            Prediction từ evidence
          </span>
        </div>
      </div>
      <div className="queue-viewer-timeline">
        <Badge tone="neutral">
          {qaCase.sourceSplit} · {qaCase.sourceImageId}
        </Badge>
      </div>
    </div>
  );
}
