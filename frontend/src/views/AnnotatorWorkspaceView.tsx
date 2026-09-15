import {
  Bot,
  BoxSelect,
  ChevronLeft,
  ChevronRight,
  Eye,
  EyeOff,
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
  type CSSProperties,
  type PointerEvent as ReactPointerEvent,
  type WheelEvent as ReactWheelEvent,
  type FormEvent,
} from "react";
import { useSearchParams } from "react-router-dom";
import {
  useImageAnnotationsQuery,
  useQaCasesQuery,
  useRealDatasetFrameSamplesQuery,
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
import { labelGuardianApiV1 } from "../api/labelGuardianApi";
import "../styles/label-editor.css";
import { boxIntersectsImage } from "../utils/realDataset";
import { classColorForLabel } from "../utils/labelColor";

type EditorTool = "select" | "move" | "box" | "zoom" | "pan";
type ResizeHandle = "nw" | "ne" | "sw" | "se";

const highPriorityImageProps = { fetchpriority: "high" } as const;
const EDITOR_FRAME_SAMPLE_LIMIT = 20;

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
    color: classColorForLabel(item.className),
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
  const selectedDataset = searchParameters.get("dataset") || "nuscenes";
  const [requestedSplit] = useState(
    searchParameters.get("split") ||
      import.meta.env.VITE_DATASET_DEFAULT_SPLIT ||
      "product",
  );
  const [selectedImageId, setSelectedImageId] = useState(
    searchParameters.get("imageId") || "",
  );
  const samplesQuery = useRealDatasetFrameSamplesQuery(
    requestedSplit || undefined,
    0,
    selectedDataset,
    undefined,
    EDITOR_FRAME_SAMPLE_LIMIT,
  );
  const split = requestedSplit || samplesQuery.data?.split || "";
  const frames = useMemo(
    () => samplesQuery.data?.results.flatMap((sample) => sample.cameras) ?? [],
    [samplesQuery.data],
  );

  const [selectedSequence, setSelectedSequence] = useState<string>("");
  const [selectedSampleId, setSelectedSampleId] = useState<string>("");

  const allSamples = samplesQuery.data?.results ?? [];
  const sequences = useMemo(() => {
    return [...new Set(allSamples.map((sample) => sample.sequenceId))].sort();
  }, [allSamples]);

  const activeFrame = useMemo(() => {
    return frames.find((item) => item.id === selectedImageId);
  }, [frames, selectedImageId]);

  const activeSample = useMemo(() => {
    if (!activeFrame) return null;
    return allSamples.find((sample) =>
      sample.cameras.some((cam) => cam.id === activeFrame.id),
    );
  }, [allSamples, activeFrame]);

  useEffect(() => {
    if (activeSample) {
      setSelectedSequence(activeSample.sequenceId);
      setSelectedSampleId(activeSample.id);
    }
  }, [activeSample]);

  const filteredSamplesForDropdown = useMemo(() => {
    if (!selectedSequence) return allSamples;
    return allSamples.filter((s) => s.sequenceId === selectedSequence);
  }, [allSamples, selectedSequence]);

  const handleSequenceChange = (nextSeq: string) => {
    setSelectedSequence(nextSeq);
    const seqSamples = allSamples.filter((s) => s.sequenceId === nextSeq);
    if (seqSamples.length > 0 && seqSamples[0]) {
      const nextSample = seqSamples[0];
      setSelectedSampleId(nextSample.id);
      if (nextSample.cameras.length > 0 && nextSample.cameras[0]) {
        setSelectedImageId(nextSample.cameras[0].id);
        updateSelectedImageInUrl(nextSample.cameras[0].id);
      }
    }
  };

  const handleSampleChange = (nextSampleId: string) => {
    setSelectedSampleId(nextSampleId);
    const nextSample = allSamples.find((s) => s.id === nextSampleId);
    if (nextSample && nextSample.cameras.length > 0 && nextSample.cameras[0]) {
      setSelectedImageId(nextSample.cameras[0].id);
      updateSelectedImageInUrl(nextSample.cameras[0].id);
    }
  };

  const activeSampleIndex = useMemo(() => {
    if (!selectedSampleId) return -1;
    return filteredSamplesForDropdown.findIndex(
      (s) => s.id === selectedSampleId,
    );
  }, [filteredSamplesForDropdown, selectedSampleId]);

  const totalFramesInScene = filteredSamplesForDropdown.length;
  const pageIndex = Math.max(
    0,
    Math.floor((activeSampleIndex >= 0 ? activeSampleIndex : 0) / 10),
  );
  const totalPages = Math.ceil(totalFramesInScene / 10);

  const paginatedSamples = useMemo(() => {
    return filteredSamplesForDropdown.slice(
      pageIndex * 10,
      (pageIndex + 1) * 10,
    );
  }, [filteredSamplesForDropdown, pageIndex]);

  const startFrame = totalFramesInScene > 0 ? pageIndex * 10 + 1 : 0;
  const endFrame = Math.min((pageIndex + 1) * 10, totalFramesInScene);

  const [jumpInput, setJumpInput] = useState("");

  const handleJumpSubmit = (e: FormEvent) => {
    e.preventDefault();
    const val = parseInt(jumpInput, 10);
    if (!isNaN(val) && val >= 1 && val <= totalFramesInScene) {
      const targetSample = filteredSamplesForDropdown[val - 1];
      if (targetSample && targetSample.cameras.length > 0) {
        switchFrame(targetSample.cameras[0]);
      }
    }
    setJumpInput("");
  };

  const handlePrevPage = () => {
    if (pageIndex > 0) {
      const prevPageFirstSampleIndex = (pageIndex - 1) * 10;
      const targetSample = filteredSamplesForDropdown[prevPageFirstSampleIndex];
      if (targetSample && targetSample.cameras.length > 0) {
        switchFrame(targetSample.cameras[0]);
      }
    }
  };

  const handleNextPage = () => {
    if (pageIndex < totalPages - 1) {
      const nextPageFirstSampleIndex = (pageIndex + 1) * 10;
      const targetSample = filteredSamplesForDropdown[nextPageFirstSampleIndex];
      if (targetSample && targetSample.cameras.length > 0) {
        switchFrame(targetSample.cameras[0]);
      }
    }
  };

  const stripRef = useRef<HTMLDivElement>(null);
  const handleWheelScroll = (e: ReactWheelEvent<HTMLDivElement>) => {
    if (stripRef.current) {
      stripRef.current.scrollLeft += e.deltaY;
    }
  };
  const annotationQuery = useImageAnnotationsQuery(
    split,
    selectedImageId || undefined,
  );
  const suggestionsQuery = useQaCasesQuery(
    { split, sourceImageId: selectedImageId || undefined },
    Boolean(selectedImageId),
  );
  const saveMutation = useSaveAnnotationsMutation();
  const document = annotationQuery.data;
  const frame: RealDatasetImageDto | undefined =
    document?.image ?? frames.find((item) => item.id === selectedImageId);
  const frameAsset = useAuthenticatedAssetUrl(frame?.imageUrl);

  const [objects, setObjects] = useState<EditableObject[]>([]);
  const [selectedObjectId, setSelectedObjectId] = useState<string | null>(null);
  const [activeTool, setActiveTool] = useState<EditorTool>("select");
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [past, setPast] = useState<EditableObject[][]>([]);
  const [future, setFuture] = useState<EditableObject[][]>([]);
  const [dirty, setDirty] = useState(false);
  const [note, setNote] = useState("");
  const [message, setMessage] = useState("");
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
      agentSuggestions.filter((suggestion) => {
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
      }),
    [agentSuggestions, canvasHeight, canvasWidth, inImageObjectIds],
  );
  const synchronizedSuggestionId = useMemo(
    () =>
      agentHighlightedSuggestionId ??
      displayedAgentSuggestions.find(
        (suggestion) =>
          Boolean(selectedObjectId) &&
          suggestion.targetTrackId === selectedObjectId,
      )?.id ??
      null,
    [agentHighlightedSuggestionId, displayedAgentSuggestions, selectedObjectId],
  );
  const selectObject = useCallback((objectId: string | null) => {
    setSelectedObjectId(objectId);
    setAgentHighlightedSuggestionId(null);
    setAgentHighlightedPrediction(null);
  }, []);
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
    if (window.document.hidden || !selectedImageId) return;
    const index = frames.findIndex((img) => img.id === selectedImageId);
    if (index === -1) return;

    const connection = navigator.connection;
    if (
      connection &&
      (connection.saveData ||
        connection.effectiveType === "slow-2g" ||
        connection.effectiveType === "2g")
    ) {
      return;
    }

    const prefetchImage = (img?: RealDatasetImageDto) => {
      if (!img) return;
      labelGuardianApiV1.fetchAsset(img.imageUrl).catch(() => {});
    };

    prefetchImage(frames[index + 1]);
    prefetchImage(frames[index - 1]);
  }, [selectedImageId, frames]);

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
    if (!selectedObject) return;
    commit(objects.filter((item) => item.id !== selectedObject.id));
    selectObject(null);
  }, [commit, objects, selectObject, selectedObject]);

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

  const zoomAtPoint = (nextZoom: number, anchor: { x: number; y: number }) => {
    const boundedZoom = clamp(nextZoom, 0.5, 5);
    if (boundedZoom === zoom) return;
    setPan((current) => ({
      x: anchor.x - ((anchor.x - current.x) / zoom) * boundedZoom,
      y: anchor.y - ((anchor.y - current.y) / zoom) * boundedZoom,
    }));
    setZoom(boundedZoom);
  };

  const zoomAtCenter = (nextZoom: number) =>
    zoomAtPoint(nextZoom, { x: canvasWidth / 2, y: canvasHeight / 2 });

  const startPan = (event: ReactPointerEvent<SVGElement>) => {
    event.preventDefault();
    svgRef.current?.setPointerCapture(event.pointerId);
    gestureRef.current = {
      type: "pan",
      start: getPoint(event, false),
      originalObjects: [],
      originalPan: { ...pan },
    };
  };

  const stagePointerDown = (event: ReactPointerEvent<SVGSVGElement>) => {
    const shouldPan = activeTool === "pan" || event.button === 2;
    if (!shouldPan && event.button !== 0) return;
    const point = getPoint(event);
    setAgentHighlightedSuggestionId(null);
    setAgentHighlightedPrediction(null);
    if (shouldPan) {
      startPan(event);
    } else if (activeTool === "box") {
      svgRef.current?.setPointerCapture(event.pointerId);
      const id = `annotation-${globalThis.crypto?.randomUUID?.() ?? Date.now()}`;
      const next: EditableObject = {
        id,
        label: labelOptions[0] ?? "car",
        trackId: "",
        bbox: { x: point.x, y: point.y, width: 1, height: 1 },
        attributes: {},
        color: classColorForLabel(labelOptions[0] ?? "car"),
        visible: true,
      };
      gestureRef.current = {
        type: "create",
        objectId: id,
        start: point,
        originalObjects: cloneObjects(objects),
      };
      setObjects([...objects, next]);
      selectObject(id);
    } else if (activeTool === "zoom") {
      zoomAtPoint(
        zoom + (event.shiftKey ? -0.25 : 0.25),
        getPoint(event, false),
      );
    } else {
      selectObject(null);
    }
  };

  const objectPointerDown = (
    event: ReactPointerEvent<SVGRectElement>,
    object: EditableObject,
  ) => {
    event.stopPropagation();
    if (event.button === 2 || activeTool === "pan") {
      startPan(event);
      return;
    }
    selectObject(object.id);
    if (!["select", "move"].includes(activeTool)) return;
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
    if (!selectedObject) return;
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
        selectObject(null);
      } else {
        setPast((history) => [...history, gesture.originalObjects].slice(-50));
        setFuture([]);
        setDirty(true);
      }
    }
    gestureRef.current = null;
  };

  const updateSelected = (changes: Partial<EditableObject>) => {
    if (!selectedObject) return;
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
            <small>Edit labels</small>
          </div>
          <div className="editor-tool-list">
            {tools.map((tool) => {
              const Icon = tool.icon;
              return (
                <button
                  className={activeTool === tool.id ? "is-active" : ""}
                  key={tool.id}
                  type="button"
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
              disabled={!selectedObject}
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
                className={selectedObjectId === object.id ? "is-selected" : ""}
                key={object.id}
                type="button"
                aria-pressed={selectedObjectId === object.id}
                onClick={() => selectObject(object.id)}
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
              <span
                className={`editor-validation-status ${validationMessages.length ? "is-error" : "is-ok"}`}
                title={
                  validationMessages.join("\n") || "Tất cả bounding box hợp lệ"
                }
              >
                {validationMessages.length
                  ? `Validation · ${validationMessages.length} lỗi`
                  : "Validation · OK"}
              </span>
            </div>
            <div className="editor-zoom-controls">
              <button
                type="button"
                aria-label="Thu nhỏ"
                onClick={() => zoomAtCenter(zoom - 0.25)}
              >
                −
              </button>
              <input
                className="editor-zoom-slider"
                type="range"
                min="50"
                max="500"
                step="10"
                value={Math.round(zoom * 100)}
                aria-label="Mức zoom"
                style={
                  {
                    "--slider-progress": `${((zoom - 0.5) / 4.5) * 100}%`,
                  } as CSSProperties
                }
                onChange={(event) =>
                  zoomAtCenter(Number(event.target.value) / 100)
                }
              />
              <strong>{Math.round(zoom * 100)}%</strong>
              <button
                type="button"
                aria-label="Phóng to"
                onClick={() => zoomAtCenter(zoom + 0.25)}
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
              onContextMenu={(event) => event.preventDefault()}
              onWheel={(event: ReactWheelEvent<SVGSVGElement>) => {
                event.preventDefault();
                const matrix = svgRef.current?.getScreenCTM();
                if (!matrix || !svgRef.current) return;
                const point = svgRef.current.createSVGPoint();
                point.x = event.clientX;
                point.y = event.clientY;
                const anchor = point.matrixTransform(matrix.inverse());
                zoomAtPoint(zoom + (event.deltaY < 0 ? 0.2 : -0.2), anchor);
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
                  {...highPriorityImageProps}
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
                  const { x, y, width, height } = object.bbox;
                  const handles: Array<[ResizeHandle, number, number]> = [
                    ["nw", x, y],
                    ["ne", x + width, y],
                    ["sw", x, y + height],
                    ["se", x + width, y + height],
                  ];
                  return (
                    <g
                      className={`editor-box ${selected ? "is-selected" : ""}`}
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
                      {selected
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
              {activeTool === "box"
                ? "Kéo trên ảnh để tạo bounding box"
                : activeTool === "pan"
                  ? "Kéo để di chuyển ảnh · lăn chuột để zoom"
                  : activeTool === "zoom"
                    ? "Click để zoom · Shift + click để thu nhỏ · chuột phải để pan"
                    : "Chọn box để kéo hoặc resize · lăn chuột để zoom · chuột phải để pan"}
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
              <button type="button" onClick={() => selectObject(null)}>
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
                        suggestion.id === synchronizedSuggestionId
                          ? "is-selected"
                          : ""
                      }
                      type="button"
                      key={suggestion.id}
                      aria-pressed={suggestion.id === synchronizedSuggestionId}
                      onClick={() => {
                        const prediction = predictionForSuggestion(suggestion);
                        setAgentHighlightedSuggestionId(suggestion.id);
                        setAgentHighlightedPrediction(
                          suggestion.targetTrackId ? null : prediction,
                        );
                        setSelectedObjectId(suggestion.targetTrackId);
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
                      onChange={(event) =>
                        updateSelected({
                          label: event.target.value,
                          color: classColorForLabel(event.target.value),
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
                <section className="editor-save-note-section">
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
        {/* Navigation Dropdowns */}
        <div className="editor-nav-selectors">
          <div className="editor-selector-group">
            <span>Sequence</span>
            <select
              className="editor-select-box"
              value={selectedSequence}
              onChange={(e) => handleSequenceChange(e.target.value)}
            >
              {sequences.map((seq) => (
                <option key={seq} value={seq}>
                  {seq}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* 10-Frame Sequence Strip (Middle Section) */}
        <div
          className="editor-frame-strip"
          ref={stripRef}
          onWheel={handleWheelScroll}
        >
          {paginatedSamples.map((sample, sampleIndex) => {
            const absoluteFrameNum = pageIndex * 10 + sampleIndex + 1;
            const isSampleActive = sample.id === selectedSampleId;
            return (
              <section
                className={`editor-frame-group ${isSampleActive ? "is-active-group" : ""}`}
                key={sample.id}
              >
                <header
                  onClick={() => handleSampleChange(sample.id)}
                  title={`Switch to Frame ${absoluteFrameNum}`}
                >
                  <strong>
                    Frame {String(absoluteFrameNum).padStart(2, "0")}
                  </strong>
                  <small>{sample.sequenceId}</small>
                </header>
                <div className="editor-camera-strip">
                  {sample.cameras.map((item, cameraIndex) => (
                    <button
                      className={item.id === frame.id ? "is-active" : ""}
                      type="button"
                      key={item.id}
                      onClick={() => switchFrame(item)}
                    >
                      <span className="frame-thumb">
                        <AuthenticatedImage sourcePath={item.imageUrl} alt="" />
                        {dirty && item.id === frame.id ? <i /> : null}
                      </span>
                      <small>
                        <b>{String(cameraIndex + 1).padStart(2, "0")}</b>
                        <span>
                          {item.cameraChannel?.replace("CAM_", "") ?? "Camera"}
                        </span>
                      </small>
                    </button>
                  ))}
                </div>
              </section>
            );
          })}
        </div>

        {/* Playback, Page Changer, Jump to Frame, and Counter Controls (Right Column) */}
        <div className="editor-sequence-controls">
          {/* Row 1: Camera Playback & Frame Jump */}
          <div className="editor-sequence-control-row">
            <form onSubmit={handleJumpSubmit} className="editor-jump-container">
              <input
                className="editor-jump-input"
                type="number"
                min="1"
                max={totalFramesInScene || 1}
                placeholder="Jump..."
                value={jumpInput}
                onChange={(e) => setJumpInput(e.target.value)}
                aria-label="Nhập số frame để chuyển nhanh"
              />
              <button className="editor-jump-btn" type="submit">
                Go
              </button>
            </form>

            <div className="editor-playback-controls">
              <button
                type="button"
                onClick={() => void annotationQuery.refetch()}
                title="Reload revision"
              >
                <RotateCcw size={17} />
              </button>
            </div>
          </div>

          {/* Row 2: Page Changer Buttons */}
          <div className="editor-page-switcher">
            <button
              className="editor-page-btn"
              type="button"
              disabled={pageIndex === 0}
              onClick={handlePrevPage}
              title="Trang trước (10 frames trước)"
            >
              &lt; Page
            </button>
            <button
              className="editor-page-btn"
              type="button"
              disabled={pageIndex >= totalPages - 1}
              onClick={handleNextPage}
              title="Trang sau (10 frames tiếp)"
            >
              Page &gt;
            </button>
          </div>

          {/* Row 3: Frame Counter (Custom Page Counter format) */}
          <div className="editor-frame-counter editor-frame-counter-compact">
            <strong>
              {startFrame}-{endFrame}
            </strong>
            <span>/ {totalFramesInScene} frames in scene</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
