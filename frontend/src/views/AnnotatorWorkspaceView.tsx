import {
  Bot,
  BoxSelect,
  ChevronLeft,
  ChevronRight,
  Eye,
  EyeOff,
  History,
  Hand,
  MousePointer2,
  Move,
  Redo2,
  RotateCcw,
  Save,
  Search,
  ShieldAlert,
  Trash2,
  Undo2,
  X,
} from "lucide-react";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
  type WheelEvent as ReactWheelEvent,
} from "react";
import { useSearchParams } from "react-router-dom";
import {
  useAnnotationHistoryQuery,
  useImageAnnotationsQuery,
  useQaCasesQuery,
  useRealDatasetFrameSamplesQuery,
  useRestoreAnnotationsMutation,
  useSaveAnnotationsMutation,
} from "../api/queries";
import type {
  QaCaseDto,
  QaPredictionEvidenceDto,
  RealDatasetImageDto,
  RealDatasetLabelDto,
} from "../api/types";
import {
  AuthenticatedImage,
  useAuthenticatedAssetUrl,
} from "../components/AuthenticatedImage";
import "../styles/label-editor.css";
import { boxIntersectsImage } from "../utils/realDataset";

type EditorTool = "select" | "move" | "box" | "zoom" | "pan";
type ResizeHandle = "nw" | "ne" | "sw" | "se";

interface EditableObject {
  id: string;
  label: string;
  trackId?: string;
  bbox: { x: number; y: number; width: number; height: number };
  attributes: Record<string, boolean | number | string>;
  color: string;
  visible: boolean;
}

interface GestureState {
  type: "move" | "resize" | "create" | "pan";
  objectId?: string;
  handle?: ResizeHandle;
  start: { x: number; y: number };
  originalBox?: EditableObject["bbox"];
  originalObjects: EditableObject[];
  originalPan?: { x: number; y: number };
}

const labelColors: Record<string, string> = {
  car: "#5b8cff",
  van: "#9c7cff",
  truck: "#ffad5b",
  pedestrian: "#45d7a8",
  cyclist: "#f36fa0",
  bicycle: "#f4d35e",
  "vehicle.car": "#5b8cff",
};
const defaultLabels = [
  "car",
  "van",
  "truck",
  "pedestrian",
  "cyclist",
  "bicycle",
];
const EMPTY_QA_CASES: QaCaseDto[] = [];
const tools = [
  {
    id: "select" as const,
    label: "Select",
    shortcut: "V",
    icon: MousePointer2,
  },
  { id: "move" as const, label: "Move", shortcut: "M", icon: Move },
  { id: "box" as const, label: "Bounding Box", shortcut: "B", icon: BoxSelect },
  { id: "zoom" as const, label: "Zoom", shortcut: "Z", icon: Search },
  { id: "pan" as const, label: "Pan", shortcut: "H", icon: Hand },
];

const cloneObjects = (objects: EditableObject[]) =>
  objects.map((item) => ({
    ...item,
    bbox: { ...item.bbox },
    attributes: { ...item.attributes },
  }));
const clamp = (value: number, minimum: number, maximum: number) =>
  Math.min(maximum, Math.max(minimum, value));

function fromLabels(labels: RealDatasetLabelDto[]): EditableObject[] {
  return labels.map((item) => ({
    id: item.id,
    label: item.className,
    trackId: item.trackId ?? undefined,
    bbox: {
      x: item.bbox.x1,
      y: item.bbox.y1,
      width: item.bbox.x2 - item.bbox.x1,
      height: item.bbox.y2 - item.bbox.y1,
    },
    attributes: { ...(item.attributes ?? {}) },
    color: labelColors[item.className] ?? "#5b8cff",
    visible: true,
  }));
}

function toLabels(objects: EditableObject[]): RealDatasetLabelDto[] {
  return objects.map((item) => ({
    id: item.id,
    className: item.label,
    trackId: item.trackId ?? null,
    attributes: item.attributes,
    bbox: {
      x1: item.bbox.x,
      y1: item.bbox.y,
      x2: item.bbox.x + item.bbox.width,
      y2: item.bbox.y + item.bbox.height,
    },
  }));
}

function predictionForSuggestion(
  suggestion: QaCaseDto,
): QaPredictionEvidenceDto | null {
  const issueEvidence = suggestion.evidence.issueEvidence;
  if (!issueEvidence || typeof issueEvidence !== "object") return null;
  const predictionIndex = (issueEvidence as Record<string, unknown>)[
    "prediction_index"
  ];
  if (typeof predictionIndex !== "number" || !Number.isInteger(predictionIndex))
    return null;
  return suggestion.evidence.observedPredictions?.[predictionIndex] ?? null;
}

export function AnnotatorWorkspaceView({
  actorId,
  onExit,
  onOpenQaCases,
}: {
  actorId: string;
  onExit: () => void;
  onOpenQaCases: (split: string, imageId: string) => void;
}) {
  const [searchParameters, setSearchParameters] = useSearchParams();
  const [requestedSplit] = useState(searchParameters.get("split") || "");
  const selectedDataset = searchParameters.get("dataset") || undefined;
  const [selectedImageId, setSelectedImageId] = useState(
    searchParameters.get("imageId") || "",
  );
  const samplesQuery = useRealDatasetFrameSamplesQuery(
    requestedSplit || undefined,
    0,
    selectedDataset,
  );
  const split = requestedSplit || samplesQuery.data?.split || "";
  const frames = useMemo(
    () => samplesQuery.data?.results.flatMap((sample) => sample.cameras) ?? [],
    [samplesQuery.data],
  );
  const annotationQuery = useImageAnnotationsQuery(
    split,
    selectedImageId || undefined,
  );
  const historyQuery = useAnnotationHistoryQuery(
    split,
    selectedImageId || undefined,
  );
  const suggestionsQuery = useQaCasesQuery(
    { split, sourceImageId: selectedImageId || undefined },
    Boolean(selectedImageId),
  );
  const saveMutation = useSaveAnnotationsMutation();
  const restoreMutation = useRestoreAnnotationsMutation();
  const document = annotationQuery.data;
  const frame: RealDatasetImageDto | undefined =
    document?.image ?? frames.find((item) => item.id === selectedImageId);
  const frameAsset = useAuthenticatedAssetUrl(frame?.imageUrl);

  const [objects, setObjects] = useState<EditableObject[]>([]);
  const [selectedObjectId, setSelectedObjectId] = useState<string | null>(null);
  const [activeTool, setActiveTool] = useState<EditorTool>("select");
  const [mode, setMode] = useState<"review" | "edit">("edit");
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [past, setPast] = useState<EditableObject[][]>([]);
  const [future, setFuture] = useState<EditableObject[][]>([]);
  const [dirty, setDirty] = useState(false);
  const [note, setNote] = useState("");
  const [message, setMessage] = useState("");
  const [activeTab, setActiveTab] = useState<"validation" | "history">(
    "validation",
  );
  const [agentHighlightedObjectId, setAgentHighlightedObjectId] = useState<
    string | null
  >(null);
  const [agentHighlightedSuggestionId, setAgentHighlightedSuggestionId] =
    useState<string | null>(null);
  const [agentHighlightedPrediction, setAgentHighlightedPrediction] =
    useState<QaPredictionEvidenceDto | null>(null);
  const [imageDimensions, setImageDimensions] = useState({
    imageId: "",
    width: 1,
    height: 1,
  });
  const loadedKey = useRef("");
  const svgRef = useRef<SVGSVGElement>(null);
  const gestureRef = useRef<GestureState | null>(null);
  const updateSelectedImageInUrl = useCallback(
    (nextImageId: string, replace = false) => {
      const next = new URLSearchParams(searchParameters);
      next.set("split", split);
      next.set("imageId", nextImageId);
      setSearchParameters(next, { replace });
    },
    [searchParameters, setSearchParameters, split],
  );

  const selectedObject =
    objects.find((item) => item.id === selectedObjectId) ?? null;
  const canvasWidth =
    imageDimensions.imageId === frame?.id
      ? imageDimensions.width
      : (frame?.width ?? 1);
  const canvasHeight =
    imageDimensions.imageId === frame?.id
      ? imageDimensions.height
      : (frame?.height ?? 1);
  const inImageObjects = objects.filter((item) =>
    boxIntersectsImage(item.bbox, canvasWidth, canvasHeight),
  );
  const displayedObjects = inImageObjects.filter((item) => item.visible);
  const inImageObjectIds = useMemo(
    () => new Set(inImageObjects.map((item) => item.id)),
    [inImageObjects],
  );
  const agentSuggestions = suggestionsQuery.data?.results ?? EMPTY_QA_CASES;
  const displayedAgentSuggestions = useMemo(
    () =>
      agentSuggestions.filter(
        (suggestion) => {
          if (suggestion.targetTrackId)
            return inImageObjectIds.has(suggestion.targetTrackId);
          const prediction = predictionForSuggestion(suggestion);
          if (!prediction) return true;
          const [x, y, width, height] = prediction.bbox;
          return boxIntersectsImage(
            { x, y, width, height },
            canvasWidth,
            canvasHeight,
          );
        },
      ),
    [agentSuggestions, canvasHeight, canvasWidth, inImageObjectIds],
  );
  const labelOptions = useMemo(
    () =>
      [
        ...new Set([
          ...defaultLabels,
          ...(samplesQuery.data?.classes ?? []),
          ...objects.map((item) => item.label),
        ]),
      ].sort(),
    [objects, samplesQuery.data?.classes],
  );
  const validationMessages = useMemo(
    () =>
      objects.flatMap((item) => {
        const messages: string[] = [];
        if (item.bbox.width < 8 || item.bbox.height < 8)
          messages.push(`${item.label}: bounding box nhỏ hơn 8 px.`);
        if (!item.label.trim())
          messages.push(`${item.id}: class đang để trống.`);
        return messages;
      }),
    [objects],
  );

  useEffect(() => {
    if (!selectedImageId && frames[0]) {
      setSelectedImageId(frames[0].id);
      updateSelectedImageInUrl(frames[0].id, true);
    }
  }, [frames, selectedImageId, updateSelectedImageInUrl]);

  useEffect(() => {
    if (!document) return;
    const key = `${document.split}:${document.imageId}:${document.revision}`;
    if (loadedKey.current === key) return;
    const next = fromLabels(document.labels);
    setObjects(next);
    setSelectedObjectId(
      next.find((item) =>
        boxIntersectsImage(
          item.bbox,
          document.image.width,
          document.image.height,
        ),
      )?.id ?? null,
    );
    setAgentHighlightedObjectId(null);
    setAgentHighlightedSuggestionId(null);
    setAgentHighlightedPrediction(null);
    setImageDimensions({
      imageId: document.image.id,
      width: document.image.width,
      height: document.image.height,
    });
    setPast([]);
    setFuture([]);
    setDirty(false);
    setMessage("");
    setZoom(1);
    setPan({ x: 0, y: 0 });
    loadedKey.current = key;
  }, [document]);

  useEffect(() => {
    if (!frame) return;
    let cancelled = false;
    const probe = new window.Image();
    probe.onload = () => {
      if (!cancelled && probe.naturalWidth && probe.naturalHeight) {
        setImageDimensions({
          imageId: frame.id,
          width: probe.naturalWidth,
          height: probe.naturalHeight,
        });
      }
    };
    if (!frameAsset.source) return;
    probe.src = frameAsset.source;
    return () => {
      cancelled = true;
    };
  }, [frame?.id, frameAsset.source]);

  useEffect(() => {
    const beforeUnload = (event: BeforeUnloadEvent) => {
      if (!dirty) return;
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", beforeUnload);
    return () => window.removeEventListener("beforeunload", beforeUnload);
  }, [dirty]);

  const commit = useCallback(
    (next: EditableObject[]) => {
      setPast((history) => [...history, cloneObjects(objects)].slice(-50));
      setFuture([]);
      setObjects(cloneObjects(next));
      setDirty(true);
      setMessage("");
    },
    [objects],
  );

  const undo = useCallback(() => {
    const previous = past.at(-1);
    if (!previous) return;
    setFuture((stack) => [cloneObjects(objects), ...stack]);
    setPast((history) => history.slice(0, -1));
    setObjects(cloneObjects(previous));
    setDirty(true);
  }, [objects, past]);

  const redo = useCallback(() => {
    const next = future[0];
    if (!next) return;
    setPast((history) => [...history, cloneObjects(objects)]);
    setFuture((stack) => stack.slice(1));
    setObjects(cloneObjects(next));
    setDirty(true);
  }, [future, objects]);

  const save = useCallback(
    async (goNext = false) => {
      if (!document || !frame || validationMessages.length) return;
      setMessage("");
      try {
        const result = await saveMutation.mutateAsync({
          split,
          imageId: document.imageId,
          expectedRevision: document.revision,
          labels: toLabels(objects),
          actorId,
          changeNote: note || "Saved from 2D Editor",
        });
        loadedKey.current = `${result.split}:${result.imageId}:${result.revision}`;
        setDirty(false);
        setPast([]);
        setFuture([]);
        setNote("");
        setMessage(`Đã lưu revision ${result.revision}.`);
        if (goNext) {
          const index = frames.findIndex(
            (item) => item.id === document.imageId,
          );
          const next = frames[index + 1];
          if (next) {
            setSelectedImageId(next.id);
            updateSelectedImageInUrl(next.id);
          }
        }
      } catch (error) {
        setMessage(
          error instanceof Error ? error.message : "Không thể lưu annotation.",
        );
      }
    },
    [
      actorId,
      document,
      frame,
      frames,
      note,
      objects,
      saveMutation,
      split,
      updateSelectedImageInUrl,
      validationMessages.length,
    ],
  );

  const deleteSelected = useCallback(() => {
    if (!selectedObject || mode === "review") return;
    commit(objects.filter((item) => item.id !== selectedObject.id));
    setSelectedObjectId(null);
  }, [commit, mode, objects, selectedObject]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target?.matches("input, textarea, select")) return;
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
        event.preventDefault();
        void save(false);
      } else if (
        (event.ctrlKey || event.metaKey) &&
        event.key.toLowerCase() === "z"
      ) {
        event.preventDefault();
        event.shiftKey ? redo() : undo();
      } else if (
        (event.ctrlKey || event.metaKey) &&
        event.key.toLowerCase() === "y"
      ) {
        event.preventDefault();
        redo();
      } else if (event.key === "Delete" || event.key === "Backspace")
        deleteSelected();
      else if (["v", "m", "b", "z", "h"].includes(event.key.toLowerCase()))
        setActiveTool(
          ({ v: "select", m: "move", b: "box", z: "zoom", h: "pan" } as const)[
            event.key.toLowerCase() as "v"
          ],
        );
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [deleteSelected, redo, save, undo]);

  if (
    samplesQuery.isPending ||
    (selectedImageId && annotationQuery.isPending)
  ) {
    return (
      <div className="label-editor-empty">
        Đang tải dataset và annotation revision…
      </div>
    );
  }
  const loadError = samplesQuery.error ?? annotationQuery.error;
  if (!frame || !document || loadError) {
    return (
      <div className="label-editor-empty">
        <strong>Không thể mở 2D Editor</strong>
        <span>
          {loadError instanceof Error
            ? loadError.message
            : "Dataset chưa có frame phù hợp."}
        </span>
        <button type="button" onClick={onExit}>
          Quay lại QA Queue
        </button>
      </div>
    );
  }

  const getPoint = (
    event: ReactPointerEvent<SVGElement>,
    imageCoordinates = true,
  ) => {
    const matrix = svgRef.current?.getScreenCTM();
    if (!matrix || !svgRef.current) return { x: 0, y: 0 };
    const point = svgRef.current.createSVGPoint();
    point.x = event.clientX;
    point.y = event.clientY;
    const raw = point.matrixTransform(matrix.inverse());
    return imageCoordinates
      ? { x: (raw.x - pan.x) / zoom, y: (raw.y - pan.y) / zoom }
      : raw;
  };

  const stagePointerDown = (event: ReactPointerEvent<SVGSVGElement>) => {
    if (event.button !== 0 || mode === "review") return;
    const point = getPoint(event);
    svgRef.current?.setPointerCapture(event.pointerId);
    setAgentHighlightedObjectId(null);
    setAgentHighlightedSuggestionId(null);
    setAgentHighlightedPrediction(null);
    if (activeTool === "box") {
      const id = `annotation-${globalThis.crypto?.randomUUID?.() ?? Date.now()}`;
      const next: EditableObject = {
        id,
        label: labelOptions[0] ?? "car",
        trackId: "",
        bbox: { x: point.x, y: point.y, width: 1, height: 1 },
        attributes: {},
        color: labelColors[labelOptions[0]] ?? "#5b8cff",
        visible: true,
      };
      gestureRef.current = {
        type: "create",
        objectId: id,
        start: point,
        originalObjects: cloneObjects(objects),
      };
      setObjects([...objects, next]);
      setSelectedObjectId(id);
    } else if (activeTool === "pan") {
      gestureRef.current = {
        type: "pan",
        start: getPoint(event, false),
        originalObjects: [],
        originalPan: { ...pan },
      };
    } else if (activeTool === "zoom")
      setZoom((value) => clamp(value + 0.2, 0.5, 3));
    else setSelectedObjectId(null);
  };

  const objectPointerDown = (
    event: ReactPointerEvent<SVGRectElement>,
    object: EditableObject,
  ) => {
    event.stopPropagation();
    setSelectedObjectId(object.id);
    setAgentHighlightedObjectId(null);
    setAgentHighlightedSuggestionId(null);
    setAgentHighlightedPrediction(null);
    if (mode === "review" || !["select", "move"].includes(activeTool)) return;
    svgRef.current?.setPointerCapture(event.pointerId);
    gestureRef.current = {
      type: "move",
      objectId: object.id,
      start: getPoint(event),
      originalBox: { ...object.bbox },
      originalObjects: cloneObjects(objects),
    };
  };

  const resizePointerDown = (
    event: ReactPointerEvent<SVGCircleElement>,
    handle: ResizeHandle,
  ) => {
    if (!selectedObject || mode === "review") return;
    event.stopPropagation();
    svgRef.current?.setPointerCapture(event.pointerId);
    gestureRef.current = {
      type: "resize",
      objectId: selectedObject.id,
      handle,
      start: getPoint(event),
      originalBox: { ...selectedObject.bbox },
      originalObjects: cloneObjects(objects),
    };
  };

  const pointerMove = (event: ReactPointerEvent<SVGSVGElement>) => {
    const gesture = gestureRef.current;
    if (!gesture) return;
    if (gesture.type === "pan") {
      const point = getPoint(event, false);
      setPan({
        x: (gesture.originalPan?.x ?? 0) + point.x - gesture.start.x,
        y: (gesture.originalPan?.y ?? 0) + point.y - gesture.start.y,
      });
      return;
    }
    const point = getPoint(event);
    setObjects((current) =>
      current.map((object) => {
        if (object.id !== gesture.objectId) return object;
        if (gesture.type === "create") {
          const x2 = clamp(point.x, 0, canvasWidth);
          const y2 = clamp(point.y, 0, canvasHeight);
          return {
            ...object,
            bbox: {
              x: Math.min(gesture.start.x, x2),
              y: Math.min(gesture.start.y, y2),
              width: Math.abs(x2 - gesture.start.x),
              height: Math.abs(y2 - gesture.start.y),
            },
          };
        }
        const original = gesture.originalBox ?? object.bbox;
        if (gesture.type === "move")
          return {
            ...object,
            bbox: {
              ...original,
              x: clamp(
                original.x + point.x - gesture.start.x,
                0,
                canvasWidth - original.width,
              ),
              y: clamp(
                original.y + point.y - gesture.start.y,
                0,
                canvasHeight - original.height,
              ),
            },
          };
        const right = original.x + original.width;
        const bottom = original.y + original.height;
        const west = gesture.handle?.includes("w");
        const north = gesture.handle?.includes("n");
        const x = west ? clamp(point.x, 0, right - 8) : original.x;
        const y = north ? clamp(point.y, 0, bottom - 8) : original.y;
        const nextRight = west
          ? right
          : clamp(point.x, original.x + 8, canvasWidth);
        const nextBottom = north
          ? bottom
          : clamp(point.y, original.y + 8, canvasHeight);
        return {
          ...object,
          bbox: { x, y, width: nextRight - x, height: nextBottom - y },
        };
      }),
    );
  };

  const commitGesture = () => {
    const gesture = gestureRef.current;
    if (!gesture) return;
    if (gesture.type !== "pan") {
      const created =
        gesture.type === "create"
          ? objects.find((item) => item.id === gesture.objectId)
          : undefined;
      if (created && (created.bbox.width < 8 || created.bbox.height < 8)) {
        setObjects(gesture.originalObjects);
        setSelectedObjectId(null);
      } else {
        setPast((history) => [...history, gesture.originalObjects].slice(-50));
        setFuture([]);
        setDirty(true);
      }
    }
    gestureRef.current = null;
  };

  const updateSelected = (changes: Partial<EditableObject>) => {
    if (!selectedObject || mode === "review") return;
    commit(
      objects.map((item) =>
        item.id === selectedObject.id ? { ...item, ...changes } : item,
      ),
    );
  };
  const updateCoordinate = (
    field: keyof EditableObject["bbox"],
    value: number,
  ) => {
    if (!selectedObject || Number.isNaN(value)) return;
    const bbox = { ...selectedObject.bbox, [field]: value };
    bbox.x = clamp(bbox.x, 0, canvasWidth - 8);
    bbox.y = clamp(bbox.y, 0, canvasHeight - 8);
    bbox.width = clamp(bbox.width, 8, canvasWidth - bbox.x);
    bbox.height = clamp(bbox.height, 8, canvasHeight - bbox.y);
    updateSelected({ bbox });
  };
  const switchFrame = (next: RealDatasetImageDto) => {
    if (
      dirty &&
      !window.confirm("Bỏ các thay đổi chưa lưu của frame hiện tại?")
    )
      return;
    loadedKey.current = "";
    setSelectedImageId(next.id);
    updateSelectedImageInUrl(next.id);
  };

  const frameIndex = frames.findIndex((item) => item.id === frame.id);
  return (
    <div className="label-editor-shell">
      <header className="editor-topbar">
        <div className="editor-breadcrumb">
          <button
            type="button"
            onClick={() => {
              if (!dirty || window.confirm("Thoát và bỏ thay đổi chưa lưu?"))
                onExit();
            }}
          >
            <ChevronLeft size={18} />
          </button>
          <div>
            <span>Label Guardian</span>
            <strong>2D Editor</strong>
          </div>
          <ChevronRight size={14} />
          <span>{split}</span>
          <ChevronRight size={14} />
          <strong>{frame.cameraChannel ?? frame.id}</strong>
        </div>
        <div className="editor-mode-switch">
          <button
            className={mode === "review" ? "is-active" : ""}
            type="button"
            onClick={() => setMode("review")}
          >
            Review
          </button>
          <button
            className={mode === "edit" ? "is-active" : ""}
            type="button"
            onClick={() => setMode("edit")}
          >
            Edit Labels
          </button>
        </div>
        <div className="editor-top-actions">
          <button type="button" onClick={undo} disabled={!past.length}>
            <Undo2 size={17} />
          </button>
          <button type="button" onClick={redo} disabled={!future.length}>
            <Redo2 size={17} />
          </button>
          <button
            className="editor-cases-button"
            type="button"
            onClick={() => {
              if (
                !dirty ||
                window.confirm("Mở QA Cases và bỏ thay đổi chưa lưu?")
              )
                onOpenQaCases(split, frame.id);
            }}
          >
            <ShieldAlert size={15} />
            QA Cases
          </button>
          <span
            className={`editor-save-state is-${dirty ? "unsaved" : "saved"}`}
          >
            <span />
            {saveMutation.isPending
              ? "Saving…"
              : dirty
                ? "Unsaved changes"
                : `Revision ${document.revision}`}
          </span>
          <button
            className="editor-save-button"
            type="button"
            disabled={
              !dirty ||
              saveMutation.isPending ||
              Boolean(validationMessages.length)
            }
            onClick={() => void save(false)}
          >
            <Save size={16} />
            Save
          </button>
          <button
            className="editor-next-button"
            type="button"
            disabled={
              !dirty ||
              saveMutation.isPending ||
              Boolean(validationMessages.length)
            }
            onClick={() => void save(true)}
          >
            Save &amp; Next
            <ChevronRight size={16} />
          </button>
        </div>
      </header>

      <main className="editor-workspace">
        <aside className="editor-left-sidebar">
          <div className="editor-sidebar-heading">
            <span>Tools</span>
            <small>{mode} mode</small>
          </div>
          <div className="editor-tool-list">
            {tools.map((tool) => {
              const Icon = tool.icon;
              return (
                <button
                  className={activeTool === tool.id ? "is-active" : ""}
                  key={tool.id}
                  type="button"
                  disabled={
                    mode === "review" &&
                    !["select", "zoom", "pan"].includes(tool.id)
                  }
                  onClick={() => setActiveTool(tool.id)}
                >
                  <Icon size={17} />
                  <span>{tool.label}</span>
                  <kbd>{tool.shortcut}</kbd>
                </button>
              );
            })}
            <button
              className="is-danger"
              type="button"
              disabled={mode === "review" || !selectedObject}
              onClick={deleteSelected}
            >
              <Trash2 size={17} />
              <span>Delete</span>
              <kbd>Del</kbd>
            </button>
          </div>
          <div className="editor-object-header">
            <span>Objects</span>
            <small>
              {inImageObjects.length}/{objects.length}
            </small>
          </div>
          <div className="editor-object-list">
            {inImageObjects.map((object, index) => (
              <button
                className={`${selectedObjectId === object.id ? "is-selected" : ""} ${agentHighlightedObjectId === object.id ? "is-agent-highlighted" : ""}`}
                key={object.id}
                type="button"
                onClick={() => {
                  setSelectedObjectId(object.id);
                  setAgentHighlightedObjectId(null);
                  setAgentHighlightedSuggestionId(null);
                  setAgentHighlightedPrediction(null);
                }}
              >
                <span
                  className="object-color"
                  style={{ background: object.color }}
                />
                <span className="object-index">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <span className="object-copy">
                  <strong>{object.label}</strong>
                  <small>{object.trackId || object.id}</small>
                </span>
                <span
                  className="object-visibility"
                  role="button"
                  tabIndex={0}
                  onClick={(event) => {
                    event.stopPropagation();
                    setObjects((current) =>
                      current.map((item) =>
                        item.id === object.id
                          ? { ...item, visible: !item.visible }
                          : item,
                      ),
                    );
                  }}
                >
                  {object.visible ? <Eye size={14} /> : <EyeOff size={14} />}
                </span>
              </button>
            ))}
            {!inImageObjects.length ? (
              <p className="editor-object-empty">
                Không có nhãn nào giao với ảnh.
                <br />
                {objects.length} nhãn ngoài ảnh vẫn được giữ trong dữ liệu.
              </p>
            ) : null}
          </div>
        </aside>

        <section className="editor-center-panel">
          <div className="editor-canvas-toolbar">
            <div>
              <span>
                {canvasWidth} × {canvasHeight}
              </span>
              <span>
                {displayedObjects.length}/{objects.length} objects displayed
              </span>
              <span>rev {document.revision}</span>
            </div>
            <div>
              <button
                type="button"
                onClick={() => setZoom((value) => clamp(value - 0.1, 0.5, 3))}
              >
                −
              </button>
              <strong>{Math.round(zoom * 100)}%</strong>
              <button
                type="button"
                onClick={() => setZoom((value) => clamp(value + 0.1, 0.5, 3))}
              >
                +
              </button>
              <button
                type="button"
                onClick={() => {
                  setZoom(1);
                  setPan({ x: 0, y: 0 });
                }}
              >
                Fit
              </button>
            </div>
          </div>
          <div className={`editor-canvas-stage tool-${activeTool}`}>
            <svg
              ref={svgRef}
              width="100%"
              height="100%"
              viewBox={`0 0 ${canvasWidth} ${canvasHeight}`}
              preserveAspectRatio="xMidYMid meet"
              onPointerDown={stagePointerDown}
              onPointerMove={pointerMove}
              onPointerUp={commitGesture}
              onPointerCancel={commitGesture}
              onWheel={(event: ReactWheelEvent<SVGSVGElement>) => {
                event.preventDefault();
                setZoom((value) =>
                  clamp(value + (event.deltaY < 0 ? 0.1 : -0.1), 0.5, 3),
                );
              }}
              aria-label={`2D annotation canvas for ${frame.filename}`}
            >
              <g transform={`translate(${pan.x} ${pan.y}) scale(${zoom})`}>
                <image
                  href={frameAsset.source || undefined}
                  x="0"
                  y="0"
                  width={canvasWidth}
                  height={canvasHeight}
                  preserveAspectRatio="none"
                />
                {agentHighlightedPrediction ? (
                  <rect
                    className="prediction-reference-box is-agent-highlighted"
                    x={agentHighlightedPrediction.bbox[0]}
                    y={agentHighlightedPrediction.bbox[1]}
                    width={agentHighlightedPrediction.bbox[2]}
                    height={agentHighlightedPrediction.bbox[3]}
                    vectorEffect="non-scaling-stroke"
                  />
                ) : null}
                {displayedObjects.map((object) => {
                  const selected = object.id === selectedObjectId;
                  const agentHighlighted =
                    object.id === agentHighlightedObjectId;
                  const { x, y, width, height } = object.bbox;
                  const handles: Array<[ResizeHandle, number, number]> = [
                    ["nw", x, y],
                    ["ne", x + width, y],
                    ["sw", x, y + height],
                    ["se", x + width, y + height],
                  ];
                  return (
                    <g
                      className={`editor-box ${selected ? "is-selected" : ""} ${agentHighlighted ? "is-agent-highlighted" : ""}`}
                      key={object.id}
                      style={{ color: object.color }}
                    >
                      <rect
                        x={x}
                        y={y}
                        width={width}
                        height={height}
                        vectorEffect="non-scaling-stroke"
                        onPointerDown={(event) =>
                          objectPointerDown(event, object)
                        }
                      />
                      <g className="editor-box-label">
                        <rect
                          x={x}
                          y={Math.max(0, y - 25 / zoom)}
                          width={
                            Math.max(84, object.label.length * 9 + 34) / zoom
                          }
                          height={25 / zoom}
                        />
                        <text
                          x={x + 8 / zoom}
                          y={Math.max(13 / zoom, y - 8 / zoom)}
                          fontSize={11 / zoom}
                        >
                          {object.label.toUpperCase()} ·{" "}
                          {String(objects.indexOf(object) + 1).padStart(2, "0")}
                        </text>
                      </g>
                      {selected && mode === "edit"
                        ? handles.map(([handle, hx, hy]) => (
                            <circle
                              className={`resize-handle handle-${handle}`}
                              key={handle}
                              cx={hx}
                              cy={hy}
                              r={6 / zoom}
                              vectorEffect="non-scaling-stroke"
                              onPointerDown={(event) =>
                                resizePointerDown(event, handle)
                              }
                            />
                          ))
                        : null}
                    </g>
                  );
                })}
              </g>
            </svg>
            {frameAsset.error ? (
              <div className="editor-canvas-error" role="alert">
                <strong>Không thể tải ảnh từ backend</strong>
                <span>{frameAsset.error}</span>
              </div>
            ) : null}
            <div className="editor-canvas-hint">
              {mode === "review"
                  ? "Review mode · geometry locked"
                  : activeTool === "box"
                    ? "Kéo trên ảnh để tạo bounding box"
                    : "Chọn box để kéo hoặc resize"}
            </div>
          </div>
          <div className="editor-detail-tabs">
            <div className="editor-tab-list">
              <button
                className={activeTab === "validation" ? "is-active" : ""}
                type="button"
                onClick={() => setActiveTab("validation")}
              >
                <ShieldAlert size={14} />
                Validation<span>{validationMessages.length}</span>
              </button>
              <button
                className={activeTab === "history" ? "is-active" : ""}
                type="button"
                onClick={() => setActiveTab("history")}
              >
                <History size={14} />
                Revision history<span>{historyQuery.data?.count ?? 0}</span>
              </button>
            </div>
            <div className="editor-tab-content">
              {activeTab === "validation" ? (
                validationMessages.length ? (
                  <div className="editor-validation-list">
                    {validationMessages.map((item) => (
                      <button type="button" key={item}>
                        <ShieldAlert size={14} />
                        <span>
                          <strong>Invalid annotation</strong>
                          {item}
                        </span>
                      </button>
                    ))}
                  </div>
                ) : (
                  <div className="editor-validation-ok">
                    <span>✓</span>
                    <div>
                      <strong>Frame validation passed</strong>
                      <small>Tất cả bounding box có cấu trúc hợp lệ.</small>
                    </div>
                  </div>
                )
              ) : (
                <div className="editor-activity-list">
                  <div>
                    <span />
                    <p>Revision 0 · Original imported labels</p>
                    <small>
                      <button
                        type="button"
                        disabled={
                          restoreMutation.isPending || document.revision === 0
                        }
                        onClick={() =>
                          void restoreMutation
                            .mutateAsync({
                              split,
                              imageId: frame.id,
                              expectedRevision: document.revision,
                              targetRevision: 0,
                              actorId,
                            })
                            .then((result) => {
                              loadedKey.current = "";
                              setMessage(
                                `Đã khôi phục thành revision ${result.revision}.`,
                              );
                            })
                        }
                      >
                        Restore
                      </button>
                    </small>
                  </div>
                  {historyQuery.data?.results.map((item) => (
                    <div key={item.revision}>
                      <span />
                      <p>
                        Revision {item.revision} · {item.labelCount} labels
                      </p>
                      <small>
                        {item.actorId ?? "unknown"} ·{" "}
                        {item.changeNote ?? "No note"}{" "}
                        <button
                          type="button"
                          disabled={
                            restoreMutation.isPending ||
                            item.revision === document.revision
                          }
                          onClick={() =>
                            void restoreMutation
                              .mutateAsync({
                                split,
                                imageId: frame.id,
                                expectedRevision: document.revision,
                                targetRevision: item.revision,
                                actorId,
                              })
                              .then(() => {
                                loadedKey.current = "";
                              })
                          }
                        >
                          Restore
                        </button>
                      </small>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </section>

        <aside className="editor-properties-panel">
          <div className="editor-properties-heading">
            <div>
              <span>Properties</span>
              <small>{selectedObject?.id ?? "No selection"}</small>
            </div>
            {selectedObject ? (
              <button type="button" onClick={() => setSelectedObjectId(null)}>
                <X size={15} />
              </button>
            ) : null}
          </div>
          <div className="editor-properties-content">
            <section className="editor-agent-suggestions-panel">
              <div className="editor-agent-suggestions-heading">
                <span>
                  <Bot size={14} />
                  <strong>Agent suggestions</strong>
                </span>
                <small>{displayedAgentSuggestions.length}</small>
              </div>
              {suggestionsQuery.isPending ? (
                <p className="editor-agent-suggestions-state">
                  Đang tải gợi ý cho ảnh hiện tại…
                </p>
              ) : suggestionsQuery.isError ? (
                <p className="editor-agent-suggestions-state is-error">
                  Không thể tải Agent suggestions.
                </p>
              ) : displayedAgentSuggestions.length ? (
                <div className="editor-agent-suggestions-list">
                  {displayedAgentSuggestions.map((suggestion) => (
                    <button
                      className={
                        suggestion.id === agentHighlightedSuggestionId
                          ? "is-selected"
                          : ""
                      }
                      type="button"
                      key={suggestion.id}
                      onClick={() => {
                        const prediction = predictionForSuggestion(suggestion);
                        setAgentHighlightedSuggestionId(suggestion.id);
                        setAgentHighlightedPrediction(
                          suggestion.targetTrackId ? null : prediction,
                        );
                        setSelectedObjectId(suggestion.targetTrackId);
                        setAgentHighlightedObjectId(suggestion.targetTrackId);
                        if (suggestion.targetTrackId) {
                          setObjects((current) =>
                            current.map((item) =>
                              item.id === suggestion.targetTrackId
                                ? { ...item, visible: true }
                                : item,
                            ),
                          );
                        }
                        if (!suggestion.targetTrackId && !prediction) {
                          setMessage(
                            "Suggestion này không chứa prediction bbox để highlight.",
                          );
                        }
                        setActiveTool("select");
                        setZoom(1);
                        setPan({ x: 0, y: 0 });
                      }}
                    >
                      <span
                        className={`editor-suggestion-severity is-${suggestion.priority}`}
                      >
                        {suggestion.priority}
                      </span>
                      <span>
                        <strong>
                          {suggestion.className} · {suggestion.errorType}
                        </strong>
                        <small>{suggestion.recommendation}</small>
                      </span>
                    </button>
                  ))}
                </div>
              ) : (
                <p className="editor-agent-suggestions-state">
                  Ảnh này chưa có suggestion trong QA Cases.
                </p>
              )}
            </section>
            {selectedObject ? (
              <>
              <section>
                <h3>Annotation</h3>
                <label>
                  <span>Label</span>
                  <select
                    value={selectedObject.label}
                    disabled={mode === "review"}
                    onChange={(event) =>
                      updateSelected({
                        label: event.target.value,
                        color:
                          labelColors[event.target.value] ??
                          selectedObject.color,
                      })
                    }
                  >
                    {labelOptions.map((label) => (
                      <option key={label}>{label}</option>
                    ))}
                  </select>
                </label>
                <label>
                  <span>Track ID</span>
                  <input
                    value={selectedObject.trackId ?? ""}
                    disabled={mode === "review"}
                    onChange={(event) =>
                      updateSelected({ trackId: event.target.value })
                    }
                  />
                </label>
                <label>
                  <span>Color</span>
                  <input
                    type="color"
                    value={selectedObject.color}
                    disabled={mode === "review"}
                    onChange={(event) =>
                      updateSelected({ color: event.target.value })
                    }
                  />
                </label>
              </section>
              <section>
                <h3>Geometry</h3>
                <div className="editor-coordinate-grid">
                  {(["x", "y", "width", "height"] as const).map((field) => (
                    <label key={field}>
                      <span>{field}</span>
                      <input
                        type="number"
                        value={Math.round(selectedObject.bbox[field])}
                        disabled={mode === "review"}
                        onChange={(event) =>
                          updateCoordinate(field, Number(event.target.value))
                        }
                      />
                    </label>
                  ))}
                </div>
              </section>
              <section>
                <h3>Attributes</h3>
                <label className="editor-toggle-row">
                  <span>
                    <strong>Occluded</strong>
                  </span>
                  <input
                    type="checkbox"
                    checked={Boolean(selectedObject.attributes.occluded)}
                    disabled={mode === "review"}
                    onChange={(event) =>
                      updateSelected({
                        attributes: {
                          ...selectedObject.attributes,
                          occluded: event.target.checked,
                        },
                      })
                    }
                  />
                </label>
                <label className="editor-toggle-row">
                  <span>
                    <strong>Truncated</strong>
                  </span>
                  <input
                    type="checkbox"
                    checked={Boolean(selectedObject.attributes.truncated)}
                    disabled={mode === "review"}
                    onChange={(event) =>
                      updateSelected({
                        attributes: {
                          ...selectedObject.attributes,
                          truncated: event.target.checked,
                        },
                      })
                    }
                  />
                </label>
              </section>
              <section>
                <h3>Save note</h3>
                <textarea
                  value={note}
                  onChange={(event) => setNote(event.target.value)}
                  placeholder="Mô tả thay đổi cho audit…"
                  rows={3}
                />
                {message ? <small>{message}</small> : null}
              </section>
              </>
            ) : (
              <div className="editor-properties-empty">
                <BoxSelect size={30} />
                <strong>No object selected</strong>
                <p>Chọn box trên canvas hoặc trong danh sách.</p>
              </div>
            )}
          </div>
        </aside>
      </main>

      <footer className="editor-timeline">
        <div className="editor-playback-controls">
          <button
            type="button"
            disabled={frameIndex <= 0}
            onClick={() =>
              frames[frameIndex - 1] && switchFrame(frames[frameIndex - 1])
            }
          >
            <ChevronLeft size={17} />
          </button>
          <button
            type="button"
            onClick={() => void annotationQuery.refetch()}
            title="Reload revision"
          >
            <RotateCcw size={17} />
          </button>
          <button
            type="button"
            disabled={frameIndex < 0 || frameIndex >= frames.length - 1}
            onClick={() =>
              frames[frameIndex + 1] && switchFrame(frames[frameIndex + 1])
            }
          >
            <ChevronRight size={17} />
          </button>
        </div>
        <div className="editor-frame-strip">
          {frames.map((item, index) => (
            <button
              className={item.id === frame.id ? "is-active" : ""}
              type="button"
              key={item.id}
              onClick={() => switchFrame(item)}
            >
              <span className="frame-thumb">
                <AuthenticatedImage
                  sourcePath={item.imageUrl}
                  alt=""
                />
                {dirty && item.id === frame.id ? <i /> : null}
              </span>
              <small>{item.cameraChannel ?? index + 1}</small>
            </button>
          ))}
        </div>
        <div className="editor-frame-counter">
          <strong>{frameIndex >= 0 ? frameIndex + 1 : "—"}</strong>
          <span>/ {frames.length} frames</span>
        </div>
      </footer>
    </div>
  );
}
