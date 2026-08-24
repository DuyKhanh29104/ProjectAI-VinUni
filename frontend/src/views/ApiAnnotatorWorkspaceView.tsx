import { ChevronLeft, ChevronRight, Eye, Layers3, Save, Tag, ZoomIn, ZoomOut } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { labelGuardianApiV1 } from "../api/labelGuardianApi";
import { useRealDatasetFrameSamplesQuery } from "../api/queries";
import type { RealDatasetImageDto, RealDatasetLabelDto } from "../api/types";
import { Badge } from "../components/ui";
import "../styles/label-editor.css";

const PAGE_SIZE = 8;
const labelPalette = ["#5b8cff", "#45d7a8", "#ffad5b", "#f36fa0", "#9c7cff", "#f4d35e", "#36c2d6"];

function colorForLabel(label: string): string {
  const index = [...label].reduce((sum, character) => sum + character.charCodeAt(0), 0) % labelPalette.length;
  return labelPalette[index];
}

function sourceNameForStorageKey(filename: string): string {
  if (filename.includes("/nuscenes/")) return "nuScenes";
  if (filename.includes("/kitti/")) return "KITTI";
  return "Cloud dataset";
}

function AnnotationBox({
  label,
  selected,
  onSelect,
}: {
  label: RealDatasetLabelDto;
  selected: boolean;
  onSelect: () => void;
}) {
  const { x1, y1, x2, y2 } = label.bbox;
  const color = colorForLabel(label.className);
  const width = Math.max(1, x2 - x1);
  const height = Math.max(1, y2 - y1);

  return (
    <g className={`api-editor-box ${selected ? "is-selected" : ""}`} style={{ color }}>
      <rect
        x={x1}
        y={y1}
        width={width}
        height={height}
        vectorEffect="non-scaling-stroke"
        onClick={onSelect}
      />
      <g className="api-editor-box-label">
        <rect x={x1} y={Math.max(0, y1 - 25)} width={Math.max(78, label.className.length * 9 + 34)} height="25" />
        <text x={x1 + 8} y={Math.max(15, y1 - 8)}>{label.className.toUpperCase()}</text>
      </g>
    </g>
  );
}

export function ApiAnnotatorWorkspaceView({ onExit }: { onExit: () => void }) {
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedDataset = searchParams.get("dataset") || "nuscenes";
  const [split, setSplit] = useState(searchParams.get("split") || "smoke");
  const [offset, setOffset] = useState(0);
  const [selectedImageId, setSelectedImageId] = useState<string>();
  const [selectedLabelId, setSelectedLabelId] = useState<string | null>(null);
  const [zoom, setZoom] = useState(1);

  const samplesQuery = useRealDatasetFrameSamplesQuery(split, offset, selectedDataset);
  const samples = samplesQuery.data?.results ?? [];
  const images = useMemo(() => samples.flatMap((sample) => sample.cameras), [samples]);
  const selected = useMemo(
    () => images.find((image) => image.id === selectedImageId) ?? images[0],
    [images, selectedImageId],
  );
  const selectedSample = useMemo(
    () => samples.find((sample) => sample.cameras.some((camera) => camera.id === selected?.id)) ?? samples[0],
    [samples, selected?.id],
  );
  const selectedLabel = selected?.labels.find((label) => label.id === selectedLabelId) ?? selected?.labels[0] ?? null;
  const lastPage = samplesQuery.data ? offset + PAGE_SIZE >= samplesQuery.data.count : true;

  useEffect(() => {
    const urlSplit = searchParams.get("split") || "smoke";
    if (urlSplit !== split) {
      setSplit(urlSplit);
      setOffset(0);
      setSelectedImageId(undefined);
    }
  }, [searchParams, split]);

  useEffect(() => {
    if (!images.some((image) => image.id === selectedImageId)) {
      setSelectedImageId(images[0]?.id);
    }
  }, [images, selectedImageId]);

  useEffect(() => {
    setSelectedLabelId(selected?.labels[0]?.id ?? null);
    setZoom(1);
  }, [selected?.id]);

  const chooseImage = (image: RealDatasetImageDto) => {
    setSelectedImageId(image.id);
    setSelectedLabelId(image.labels[0]?.id ?? null);
  };

  const imageUrl = selected ? labelGuardianApiV1.resolveAssetUrl(selected.imageUrl) : "";
  const sourceName = selected?.dataset ? (selected.dataset === "nuscenes" ? "nuScenes" : selected.dataset.toUpperCase()) : selected ? sourceNameForStorageKey(selected.filename) : "Cloud dataset";
  const splitOptions = samplesQuery.data?.availableSplits.length ? samplesQuery.data.availableSplits : [split];
  const datasetOptions = samplesQuery.data?.availableDatasets.length ? samplesQuery.data.availableDatasets : ["nuscenes", "kitti"];

  const updateUrlFilter = (key: "dataset" | "split", value: string) => {
    const next = new URLSearchParams(searchParams);
    next.set(key, value);
    setSearchParams(next, { replace: true });
  };

  if (samplesQuery.isPending) {
    return (
      <div className="label-editor-shell api-label-editor">
        <div className="label-editor-empty">Đang tải dataset thật từ backend...</div>
      </div>
    );
  }

  if (samplesQuery.isError) {
    return (
      <div className="label-editor-shell api-label-editor">
        <div className="label-editor-empty">
          <strong>Không tải được 2D dataset</strong>
          <p>{samplesQuery.error.message}</p>
          <code>VITE_DATA_SOURCE=api · DATASET_BACKEND=database</code>
        </div>
      </div>
    );
  }

  return (
    <div className="label-editor-shell api-label-editor">
      <header className="editor-topbar api-editor-topbar">
        <div className="editor-breadcrumb">
          <button type="button" onClick={onExit} aria-label="Back to dashboard"><ChevronLeft size={18} /></button>
          <div><span>Label Guardian</span><strong>2D Label Editor</strong></div>
          <ChevronRight size={14} />
          <span>{sourceName}</span>
          <ChevronRight size={14} />
          <strong>{selectedSample?.sequenceId ?? "No frame"}</strong>
        </div>
        <div className="editor-mode-switch" aria-label="Editor mode">
          <button className="is-active" type="button">Review</button>
          <button type="button" disabled>Edit Labels</button>
        </div>
        <div className="editor-top-actions">
          <label className="api-editor-split">
            <span>Dataset</span>
            <select value={selectedDataset} onChange={(event) => { updateUrlFilter("dataset", event.target.value); setOffset(0); setSelectedImageId(undefined); }}>
              {datasetOptions.map((item) => <option key={item} value={item}>{item === "nuscenes" ? "nuScenes" : item.toUpperCase()}</option>)}
            </select>
          </label>
          <label className="api-editor-split">
            <span>Split</span>
            <select value={split} onChange={(event) => { setSplit(event.target.value); updateUrlFilter("split", event.target.value); setOffset(0); setSelectedImageId(undefined); }}>
              {splitOptions.map((item) => <option key={item}>{item}</option>)}
            </select>
          </label>
          <span className="editor-save-state"><span />Cloud synced</span>
          <button className="editor-save-button" type="button" disabled><Save size={16} />Read-only</button>
        </div>
      </header>

      <main className="editor-workspace api-editor-workspace">
        <aside className="editor-left-sidebar api-editor-samples">
          <div className="editor-sidebar-heading"><span>Frames</span><small>{samplesQuery.data?.count ?? 0}</small></div>
          <div className="api-editor-sample-list">
            {samples.map((sample, sampleIndex) => (
              <section key={sample.id} className={sample.id === selectedSample?.id ? "is-selected" : ""}>
                <button type="button" onClick={() => sample.cameras[0] && chooseImage(sample.cameras[0])}>
                  <span>
                    <strong>Frame {offset + sampleIndex + 1}</strong>
                    <small>{sample.sequenceId}</small>
                  </span>
                  <Badge tone="neutral">{sample.cameraCount} cam</Badge>
                </button>
                <div>
                  {sample.cameras.map((image) => (
                    <button
                      key={image.id}
                      className={image.id === selected?.id ? "is-active" : ""}
                      type="button"
                      onClick={() => chooseImage(image)}
                    >
                      <img src={labelGuardianApiV1.resolveAssetUrl(image.imageUrl)} alt="" loading="lazy" />
                      <span>
                        <strong>{image.cameraChannel?.replace("CAM_", "") ?? image.id}</strong>
                        <small>{image.labelCount} labels</small>
                      </span>
                    </button>
                  ))}
                </div>
              </section>
            ))}
          </div>
        </aside>

        <section className="editor-center-panel">
          <div className="editor-canvas-toolbar">
            <div>
              <span>{sourceName}</span>
              <span>{selected?.width ?? 0} x {selected?.height ?? 0}</span>
              <span>{selected?.labelCount ?? 0} objects</span>
            </div>
            <div>
              <button type="button" onClick={() => setZoom((value) => Math.max(0.5, value - 0.1))} title="Zoom out"><ZoomOut size={15} /></button>
              <strong>{Math.round(zoom * 100)}%</strong>
              <button type="button" onClick={() => setZoom((value) => Math.min(2.5, value + 0.1))} title="Zoom in"><ZoomIn size={15} /></button>
              <button type="button" onClick={() => setZoom(1)}>Fit</button>
            </div>
          </div>

          <div className="editor-canvas-stage api-editor-stage">
            {selected ? (
              <svg
                viewBox={`0 0 ${selected.width} ${selected.height}`}
                aria-label={`2D annotation canvas for ${selected.cameraChannel ?? selected.id}`}
              >
                <g transform={`scale(${zoom})`}>
                  <image href={imageUrl} x="0" y="0" width={selected.width} height={selected.height} preserveAspectRatio="xMidYMid meet" />
                  {selected.labels.map((label) => (
                    <AnnotationBox
                      key={label.id}
                      label={label}
                      selected={label.id === selectedLabel?.id}
                      onSelect={() => setSelectedLabelId(label.id)}
                    />
                  ))}
                </g>
              </svg>
            ) : (
              <div className="label-editor-empty">Split này chưa có frame trong Supabase.</div>
            )}
            <div className="editor-canvas-hint">
              {selectedSample?.sampleId ?? "No sample"} · {selected?.cameraChannel ?? selected?.filename ?? "No camera"}
            </div>
          </div>
        </section>

        <aside className="editor-properties-panel">
          <div className="editor-properties-heading">
            <div><span>Cloud metadata</span><small>{selected?.id ?? "No image"}</small></div>
            <Eye size={15} />
          </div>
          <div className="editor-properties-content api-editor-properties">
            <section>
              <h3>Frame group</h3>
              <dl>
                <div><dt>Dataset</dt><dd>{sourceName}</dd></div>
                <div><dt>Split</dt><dd>{split}</dd></div>
                <div><dt>Sequence</dt><dd>{selectedSample?.sequenceId ?? "-"}</dd></div>
                <div><dt>Sample</dt><dd>{selectedSample?.sampleId ?? "-"}</dd></div>
                <div><dt>Camera views</dt><dd>{selectedSample?.cameraCount ?? 0}</dd></div>
              </dl>
            </section>
            <section>
              <h3>Objects</h3>
              <div className="api-editor-object-list">
                {selected?.labels.map((label, index) => (
                  <button
                    key={label.id}
                    className={label.id === selectedLabel?.id ? "is-selected" : ""}
                    type="button"
                    onClick={() => setSelectedLabelId(label.id)}
                  >
                    <i style={{ background: colorForLabel(label.className) }} />
                    <span><strong>{String(index + 1).padStart(2, "0")} · {label.className}</strong><small>{Math.round(label.bbox.x1)}, {Math.round(label.bbox.y1)} - {Math.round(label.bbox.x2)}, {Math.round(label.bbox.y2)}</small></span>
                  </button>
                ))}
                {!selected?.labels.length ? <p>No normalized objects on this camera.</p> : null}
              </div>
            </section>
            <section>
              <h3>Storage path</h3>
              <code className="api-editor-storage-key">{selected?.filename ?? "-"}</code>
            </section>
          </div>
        </aside>
      </main>

      <footer className="editor-timeline api-editor-timeline">
        <div className="editor-playback-controls">
          <button type="button" disabled={offset === 0} onClick={() => { setOffset(Math.max(0, offset - PAGE_SIZE)); setSelectedImageId(undefined); }}><ChevronLeft size={17} /></button>
          <button type="button" disabled={lastPage} onClick={() => { setOffset(offset + PAGE_SIZE); setSelectedImageId(undefined); }}><ChevronRight size={17} /></button>
        </div>
        <div className="api-editor-camera-strip">
          {images.map((image) => (
            <button key={image.id} className={image.id === selected?.id ? "is-active" : ""} type="button" onClick={() => chooseImage(image)}>
              <img src={labelGuardianApiV1.resolveAssetUrl(image.imageUrl)} alt="" loading="lazy" />
              <span><Layers3 size={13} />{image.cameraChannel?.replace("CAM_", "") ?? image.id}</span>
              <small><Tag size={12} />{image.labelCount}</small>
            </button>
          ))}
        </div>
        <div className="editor-frame-counter"><strong>{Math.floor(offset / PAGE_SIZE) + 1}</strong><span>/ pages</span></div>
      </footer>
    </div>
  );
}
