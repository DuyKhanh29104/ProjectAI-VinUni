import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type PointerEvent as ReactPointerEvent,
} from "react";
import {
  ChevronLeft,
  ChevronRight,
  Hand,
  ImageOff,
  Maximize2,
  Minus,
  MousePointer2,
  Plus,
  Ruler,
} from "lucide-react";
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
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const dragOriginRef = useRef<{
    pointerId: number;
    clientX: number;
    clientY: number;
    panX: number;
    panY: number;
  } | null>(null);

  useEffect(() => {
    setFrameId(finding?.frameId ?? "");
    setZoom(100);
    setPan({ x: 0, y: 0 });
  }, [finding?.frameId, finding?.id]);

  const sceneFrames = useMemo(
    () =>
      state.frames
        .filter((frame) => frame.sceneId === finding?.sceneId)
        .sort((first, second) => first.frameNumber - second.frameNumber),
    [finding?.sceneId, state.frames],
  );
  const frameIndex = Math.max(
    0,
    sceneFrames.findIndex((frame) => frame.id === frameId),
  );
  const frame =
    sceneFrames[frameIndex] ?? state.frames.find((item) => item.id === frameId);
  const annotations = state.annotations.filter(
    (annotation) =>
      annotation.frameId === frame?.id && annotation.layer === "original",
  );
  const predictions = state.predictions.filter(
    (prediction) => prediction.frameId === frame?.id,
  );

  if (!finding || !frame) {
    return (
      <div className="queue-comparison-empty">
        <ImageOff aria-hidden="true" size={24} />
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
      setPan({ x: 0, y: 0 });
    }
  };

  const startPan = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (event.button !== 0 || tool === "measure") return;
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    dragOriginRef.current = {
      pointerId: event.pointerId,
      clientX: event.clientX,
      clientY: event.clientY,
      panX: pan.x,
      panY: pan.y,
    };
    setIsDragging(true);
  };
  const movePan = (event: ReactPointerEvent<HTMLDivElement>) => {
    const origin = dragOriginRef.current;
    if (!origin || origin.pointerId !== event.pointerId) return;
    setPan({
      x: origin.panX + event.clientX - origin.clientX,
      y: origin.panY + event.clientY - origin.clientY,
    });
  };
  const stopPan = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (dragOriginRef.current?.pointerId !== event.pointerId) return;
    dragOriginRef.current = null;
    setIsDragging(false);
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
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
          <button
            className={tool === "select" ? "is-active" : ""}
            type="button"
            onClick={() => setTool("select")}
            aria-label="Chọn object"
            title="Chọn object"
          >
            <MousePointer2 size={15} />
          </button>
          <button
            className={tool === "pan" ? "is-active" : ""}
            type="button"
            onClick={() => setTool("pan")}
            aria-label="Di chuyển khung nhìn"
            title="Di chuyển khung nhìn"
          >
            <Hand size={15} />
          </button>
          <button
            className={tool === "measure" ? "is-active" : ""}
            type="button"
            onClick={() => setTool("measure")}
            aria-label="Đo khoảng cách"
            title="Đo khoảng cách"
          >
            <Ruler size={15} />
          </button>
          <span className="viewer-readonly-divider" />
          <Button
            size="sm"
            variant="ghost"
            onClick={() => {
              setZoom(100);
              setPan({ x: 0, y: 0 });
            }}
          >
            <Maximize2 size={14} /> Vừa khung
          </Button>
        </div>

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
            onClick={() => setZoom((current) => Math.max(75, current - 25))}
            aria-label="Thu nhỏ"
            title="Thu nhỏ"
          >
            <Minus size={14} />
          </Button>
          <span className="viewer-zoom-value">{zoom}%</span>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => setZoom((current) => Math.min(175, current + 25))}
            aria-label="Phóng to"
            title="Phóng to"
          >
            <Plus size={14} />
          </Button>
        </div>
      </div>

      <div
        className={`queue-viewer-stage tool-${tool} ${isDragging ? "is-dragging" : ""}`}
        aria-label="Kéo chuột để di chuyển ảnh"
        onPointerDown={startPan}
        onPointerMove={movePan}
        onPointerUp={stopPan}
        onPointerCancel={stopPan}
        onLostPointerCapture={stopPan}
      >
        <div
          className="queue-viewer-canvas"
          style={{
            aspectRatio: `${frame.width} / ${frame.height}`,
            transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom / 100})`,
            transformOrigin: "center",
          }}
        >
          <img
            src={frame.thumbnailUrl}
            alt={`Frame ${frame.frameNumber} dùng để so sánh nhãn`}
          />
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
                    <span>
                      {prediction.label} ·{" "}
                      {Math.round(prediction.confidence * 100)}%
                    </span>
                  </div>
                ))
              : null}
          </div>
        </div>
        <div className="queue-viewer-legend">
          <span>
            <i className="legend-box-gt" />
            GT (Ground Truth)
          </span>
          <span>
            <i className="legend-box-prediction" />
            Prediction (Model)
          </span>
        </div>
      </div>

      <div className="queue-viewer-timeline">
        <Button
          size="sm"
          variant="ghost"
          disabled={frameIndex <= 0}
          onClick={() => moveFrame(-1)}
          aria-label="Frame trước"
          title="Frame trước"
        >
          <ChevronLeft size={15} />
        </Button>
        <strong>{frame.frameNumber}</strong>
        <span>/ {sceneFrames.at(-1)?.frameNumber ?? frame.frameNumber}</span>
        <input
          type="range"
          min="0"
          max={Math.max(sceneFrames.length - 1, 0)}
          value={frameIndex}
          onChange={(event) => {
            const nextFrame = sceneFrames[Number(event.target.value)];
            if (nextFrame) {
              setFrameId(nextFrame.id);
              setPan({ x: 0, y: 0 });
            }
          }}
          aria-label="Chọn frame trong sequence"
        />
        <Button
          size="sm"
          variant="ghost"
          disabled={frameIndex >= sceneFrames.length - 1}
          onClick={() => moveFrame(1)}
          aria-label="Frame tiếp theo"
          title="Frame tiếp theo"
        >
          <ChevronRight size={15} />
        </Button>
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
