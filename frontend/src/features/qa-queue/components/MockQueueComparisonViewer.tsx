import { useEffect, useMemo, useState, type CSSProperties } from "react";
import { Badge, Button } from "../../../components/ui";
import type { Finding, MockState } from "../../../domain/types";

type ComparisonMode = "gt" | "prediction" | "both";
type ViewerTool = "select" | "pan" | "measure";

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

export function MockQueueComparisonViewer({
  state,
  finding,
}: {
  state: MockState;
  finding?: Finding;
}) {
  const [mode, setMode] = useState<ComparisonMode>("both");
  const [tool, setTool] = useState<ViewerTool>("select");
  const [zoom, setZoom] = useState(100);
  const [frameId, setFrameId] = useState(finding?.frameId ?? "");
  const [fps, setFps] = useState("10");

  useEffect(() => {
    setFrameId(finding?.frameId ?? "");
    setZoom(100);
  }, [finding?.frameId, finding?.id]);

  const sceneFrames = useMemo(
    () =>
      state.frames
        .filter((frame) => frame.sceneId === finding?.sceneId)
        .sort((first, second) => first.frameNumber - second.frameNumber),
    [finding?.sceneId, state.frames],
  );
  const frameIndex = Math.max(0, sceneFrames.findIndex((frame) => frame.id === frameId));
  const frame = sceneFrames[frameIndex] ?? state.frames.find((item) => item.id === frameId);
  const annotations = state.annotations.filter(
    (annotation) => annotation.frameId === frame?.id && annotation.layer === "original",
  );
  const predictions = state.predictions.filter(
    (prediction) => prediction.frameId === frame?.id,
  );

  if (!finding || !frame) {
    return (
      <div className="queue-comparison-empty">
        <span>◇</span>
        <strong>Chọn một case để mở viewer</strong>
        <small>Viewer chỉ dùng để so sánh GT và Prediction.</small>
      </div>
    );
  }

  const moveFrame = (offset: number) => {
    const nextIndex = Math.min(
      Math.max(frameIndex + offset, 0),
      Math.max(sceneFrames.length - 1, 0),
    );
    const nextFrame = sceneFrames[nextIndex];
    if (nextFrame) {
      setFrameId(nextFrame.id);
    }
  };

  return (
    <div className="queue-comparison-viewer">
      <div className="queue-viewer-heading">
        <div>
          <strong>Khung so sánh nhãn</strong>
          <span>Annotation revision · viewer chỉ đọc</span>
        </div>
        <Badge tone="info">Frame {frame.frameNumber}</Badge>
      </div>

      <div className="queue-viewer-toolbar">
        <div className="viewer-tool-group" aria-label="Công cụ quan sát">
          <button className={tool === "select" ? "is-active" : ""} type="button" onClick={() => setTool("select")} aria-label="Chọn object">↖</button>
          <button className={tool === "pan" ? "is-active" : ""} type="button" onClick={() => setTool("pan")} aria-label="Di chuyển khung nhìn">✥</button>
          <button className={tool === "measure" ? "is-active" : ""} type="button" onClick={() => setTool("measure")} aria-label="Đo khoảng cách">⌁</button>
          <span className="viewer-readonly-divider" />
          <Button size="sm" variant="ghost" onClick={() => setZoom(100)}>Vừa khung</Button>
        </div>

        <div className="viewer-compare-controls">
          <span>GT / Prediction</span>
          <div className="compare-segmented" role="group" aria-label="Chế độ so sánh">
            <button className={mode === "gt" ? "is-active" : ""} type="button" onClick={() => setMode("gt")}>GT</button>
            <button className={mode === "prediction" ? "is-active" : ""} type="button" onClick={() => setMode("prediction")}>Prediction</button>
            <button className={mode === "both" ? "is-active" : ""} type="button" onClick={() => setMode("both")}>Cả hai</button>
          </div>
          <Button size="sm" variant="ghost" onClick={() => setZoom((current) => Math.max(75, current - 25))}>−</Button>
          <span className="viewer-zoom-value">{zoom}%</span>
          <Button size="sm" variant="ghost" onClick={() => setZoom((current) => Math.min(175, current + 25))}>+</Button>
        </div>
      </div>

      <div className={`queue-viewer-stage tool-${tool}`}>
        <div
          className="queue-viewer-canvas"
          style={{
            aspectRatio: `${frame.width} / ${frame.height}`,
            transform: `scale(${zoom / 100})`,
          }}
        >
          <img src={frame.thumbnailUrl} alt={`Frame ${frame.frameNumber} dùng để so sánh nhãn`} />
          <div className="queue-viewer-overlays">
            {mode !== "prediction"
              ? annotations.map((annotation) => (
                  <div
                    className={`queue-overlay queue-overlay-gt ${annotation.id === finding.annotationId ? "is-selected" : ""}`}
                    key={annotation.id}
                    style={boxStyle(
                      annotation.bbox.x,
                      annotation.bbox.y,
                      annotation.bbox.width,
                      annotation.bbox.height,
                      frame.width,
                      frame.height,
                    )}
                  >
                    <span>{annotation.label} · GT</span>
                  </div>
                ))
              : null}
            {mode !== "gt"
              ? predictions.map((prediction) => (
                  <div
                    className={`queue-overlay queue-overlay-prediction ${prediction.trackId === finding.trackId ? "is-selected" : ""}`}
                    key={prediction.id}
                    style={boxStyle(
                      prediction.bbox.x,
                      prediction.bbox.y,
                      prediction.bbox.width,
                      prediction.bbox.height,
                      frame.width,
                      frame.height,
                    )}
                  >
                    <span>{prediction.label} · {Math.round(prediction.confidence * 100)}%</span>
                  </div>
                ))
              : null}
          </div>
        </div>
        <div className="queue-viewer-legend">
          <span><i className="legend-box-gt" />GT (Ground Truth)</span>
          <span><i className="legend-box-prediction" />Prediction (Model)</span>
        </div>
      </div>

      <div className="queue-viewer-timeline">
        <Button size="sm" variant="ghost" disabled={frameIndex <= 0} onClick={() => moveFrame(-1)}>‹</Button>
        <strong>{frame.frameNumber}</strong>
        <span>/ {sceneFrames.at(-1)?.frameNumber ?? frame.frameNumber}</span>
        <input
          type="range"
          min="0"
          max={Math.max(sceneFrames.length - 1, 0)}
          value={frameIndex}
          onChange={(event) => {
            const nextFrame = sceneFrames[Number(event.target.value)];
            if (nextFrame) setFrameId(nextFrame.id);
          }}
          aria-label="Chọn frame trong sequence"
        />
        <Button size="sm" variant="ghost" disabled={frameIndex >= sceneFrames.length - 1} onClick={() => moveFrame(1)}>›</Button>
        <label>
          <span className="sr-only">Tốc độ phát</span>
          <select value={fps} onChange={(event) => setFps(event.target.value)}>
            <option value="5">5 FPS</option>
            <option value="10">10 FPS</option>
            <option value="20">20 FPS</option>
          </select>
        </label>
      </div>
    </div>
  );
}
