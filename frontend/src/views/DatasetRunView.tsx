import type { ComponentType, SVGProps } from "react";
import {
  AlertTriangle,
  ArrowUpRight,
  Boxes,
  Check,
  CheckCircle2,
  CircleDashed,
  Cloud,
  Database,
  FileCheck2,
  GitCompareArrows,
  HardDrive,
  Layers3,
  LockKeyhole,
  Play,
  RefreshCcw,
  ScanSearch,
  ShieldCheck,
  SlidersHorizontal,
  UsersRound,
  Workflow,
} from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";
import { isApiDataSourceEnabled } from "../api/labelGuardianApi";
import {
  useQaCasesQuery,
  useRealDatasetFrameSamplesQuery,
} from "../api/queries";
import { Button } from "../components/ui";
import { cloudDatasets } from "../config/cloudDataset";
import type { BatchLifecycle, Role } from "../domain/types";
import { useMockData } from "../state/MockDataProvider";
import "../styles/dataset-v2.css";

type Icon = ComponentType<SVGProps<SVGSVGElement>>;
type StageState = "done" | "active" | "pending" | "blocked" | "unknown";

interface LifecycleStage {
  id: string;
  label: string;
  icon: Icon;
  state: StageState;
  detail: string;
}

interface CoverageRow {
  id: string;
  name: string;
  meta: string;
  cells: Array<"ready" | "processed" | "flagged">;
}

const lifecycleDefinitions = [
  { id: "intake", label: "Intake", icon: Cloud },
  { id: "validate", label: "Validate", icon: ShieldCheck },
  { id: "batch", label: "Batch", icon: Boxes },
  { id: "assign", label: "Assign", icon: UsersRound },
  { id: "label", label: "Label", icon: Layers3 },
  { id: "review", label: "Review", icon: ScanSearch },
  { id: "approve", label: "Approve", icon: FileCheck2 },
  { id: "export", label: "Export", icon: HardDrive },
] as const;

const lifecycleIndex: Record<BatchLifecycle, number> = {
  draft: 0,
  ready: 1,
  active: 4,
  review: 5,
  rework: 5,
  approved: 6,
  exported: 7,
};

const roleCopy: Record<Role, { label: string; title: string; note: string }> = {
  reviewer: {
    label: "QA Reviewer",
    title: "Release control",
    note: "Inspect review scope and blockers. Batch creation and frame assignment require the workflow API.",
  },
  annotator: {
    label: "Annotator",
    title: "Assigned scope",
    note: "View dataset context and open work already assigned to you. Assignment changes remain reviewer-owned.",
  },
  admin: {
    label: "Admin / ML Engineer",
    title: "Evaluation run",
    note: "Run the demo evaluator and inspect the model and rule snapshot attached to this dataset.",
  },
};

function displayTime(value?: string) {
  return value ? new Date(value).toLocaleString("vi-VN") : "Not available";
}

function percent(value: number, total: number) {
  return total > 0 ? Math.min(100, Math.round((value / total) * 100)) : 0;
}

function stageState(index: number, activeIndex: number): StageState {
  if (index < activeIndex) return "done";
  if (index === activeIndex) return "active";
  return "pending";
}

function StageMarker({ state }: { state: StageState }) {
  if (state === "done") return <Check aria-hidden="true" />;
  if (state === "blocked") return <AlertTriangle aria-hidden="true" />;
  return <CircleDashed aria-hidden="true" />;
}

export function DatasetRunView() {
  const { state, actions } = useMockData();
  const apiDataSourceEnabled = isApiDataSourceEnabled();
  const [searchParams] = useSearchParams();
  const configuredDataset = cloudDatasets[0];
  const apiDataset =
    searchParams.get("dataset") || configuredDataset?.id || "nuscenes";
  const apiSplit =
    searchParams.get("split") ||
    import.meta.env.VITE_DATASET_DEFAULT_SPLIT ||
    "product";
  const apiCasesQuery = useQaCasesQuery({});
  const apiSamplesQuery = useRealDatasetFrameSamplesQuery(
    apiSplit,
    0,
    apiDataset,
  );
  const apiCases = apiCasesQuery.data?.results ?? [];
  const apiSamples = apiSamplesQuery.data;

  const selectedDataset =
    state.datasets.find((item) => item.id === state.selectedDatasetId) ??
    state.datasets[0];
  const selectedDatasetId = apiDataSourceEnabled
    ? apiDataset
    : selectedDataset.id;
  const selectedDatasetName = apiDataSourceEnabled
    ? (configuredDataset?.name ?? apiDataset)
    : selectedDataset.name;
  const selectedVersion = apiDataSourceEnabled
    ? (configuredDataset?.version ?? "Current")
    : selectedDataset.version;
  const selectedFormat = apiDataSourceEnabled
    ? (configuredDataset?.format ?? "nuScenes")
    : selectedDataset.format;
  const activeSplit = apiDataSourceEnabled
    ? (apiSamples?.split ?? apiSplit)
    : "fixture";
  const activeRole = state.activeRole;
  const selectedBatch = state.batches.find(
    (batch) => batch.datasetId === selectedDataset.id,
  );
  const mockScenes = state.scenes.filter(
    (scene) => scene.datasetId === selectedDataset.id,
  );
  const mockFrames = state.frames.filter((frame) =>
    mockScenes.some((scene) => scene.id === frame.sceneId),
  );
  const mockFindings = state.findings.filter((finding) =>
    mockScenes.some((scene) => scene.id === finding.sceneId),
  );
  const run =
    state.qaRun.datasetId === selectedDataset.id
      ? state.qaRun
      : {
          ...state.qaRun,
          datasetId: selectedDataset.id,
          status: "idle" as const,
          progress: 0,
          processedFrames: 0,
          totalFrames: mockFrames.length,
        };
  const reviewedCases = apiCases.filter((qaCase) =>
    ["confirmed", "corrected", "rejected"].includes(qaCase.status),
  ).length;
  const highRiskCases = apiCases.filter(
    (qaCase) => qaCase.riskScore >= 80,
  ).length;

  const lifecycle: LifecycleStage[] = apiDataSourceEnabled
    ? lifecycleDefinitions.map((definition, index) => {
        if (index === 0) {
          return {
            ...definition,
            state: apiSamplesQuery.isError ? "blocked" : "done",
            detail: "Official source",
          };
        }
        if (index === 1) {
          return {
            ...definition,
            state: apiSamplesQuery.isError
              ? "blocked"
              : apiSamplesQuery.isPending
                ? "active"
                : "done",
            detail: apiSamplesQuery.isPending
              ? "Reading metadata"
              : apiSamplesQuery.isError
                ? "Source error"
                : "Metadata ready",
          };
        }
        if (index === 5 && apiCases.length > 0) {
          return {
            ...definition,
            state: "active",
            detail: `${reviewedCases}/${apiCases.length} cases`,
          };
        }
        return { ...definition, state: "unknown", detail: "Not tracked" };
      })
    : lifecycleDefinitions.map((definition, index) => {
        const activeIndex = selectedBatch
          ? lifecycleIndex[selectedBatch.state]
          : 1;
        const detailByIndex = [
          "Fixture loaded",
          selectedDataset.anonymized ? "Privacy checked" : "Review required",
          selectedBatch?.name ?? "No batch fixture",
          selectedBatch
            ? `${selectedBatch.assignedCount}/${selectedBatch.frameCount}`
            : "Not tracked",
          selectedBatch
            ? `${selectedBatch.submittedCount} submitted`
            : "Not tracked",
          selectedBatch?.state === "rework"
            ? "Rework active"
            : `${mockFindings.length} findings`,
          selectedBatch
            ? `${selectedBatch.approvedCount} approved`
            : "Not tracked",
          selectedBatch?.state === "exported"
            ? "Fixture exported"
            : "Not available",
        ];
        return {
          ...definition,
          state: stageState(index, activeIndex),
          detail: detailByIndex[index],
        };
      });

  const mockProcessedFrameIds = new Set(
    run.status === "idle"
      ? []
      : mockFrames.slice(0, run.processedFrames).map((frame) => frame.id),
  );
  const coverageRows: CoverageRow[] = apiDataSourceEnabled
    ? (apiSamples?.results ?? []).slice(0, 6).map((sample) => ({
        id: sample.id,
        name: sample.sequenceId,
        meta: `${sample.cameraCount} cameras · ${sample.labelCount} labels`,
        cells: Array.from(
          { length: Math.max(1, Math.min(12, sample.cameraCount)) },
          () => "ready" as const,
        ),
      }))
    : mockScenes.map((scene) => {
        const sceneFrames = mockFrames.filter(
          (frame) => frame.sceneId === scene.id,
        );
        const sceneHasFinding = mockFindings.some(
          (finding) => finding.sceneId === scene.id,
        );
        return {
          id: scene.id,
          name: scene.name,
          meta: `${sceneFrames.length} frames · ${scene.location}`,
          cells: sceneFrames.map((frame, index) =>
            sceneHasFinding && index === sceneFrames.length - 1
              ? "flagged"
              : mockProcessedFrameIds.has(frame.id)
                ? "processed"
                : "ready",
          ),
        };
      });

  const previewImage = apiDataSourceEnabled
    ? apiSamples?.results[0]?.cameras[0]?.imageUrl
    : mockFrames[0]?.thumbnailUrl;
  const previewLabel = apiDataSourceEnabled
    ? (apiSamples?.results[0]?.sequenceId ?? "No frame sample")
    : (mockScenes[0]?.name ?? "No scene fixture");

  const allocationRows = apiDataSourceEnabled
    ? []
    : Array.from(new Set(mockScenes.map((scene) => scene.annotatorId))).map(
        (annotatorId) => {
          const annotator = state.users.find((user) => user.id === annotatorId);
          const ownedSceneIds = new Set(
            mockScenes
              .filter((scene) => scene.annotatorId === annotatorId)
              .map((scene) => scene.id),
          );
          const frameCount = mockFrames.filter((frame) =>
            ownedSceneIds.has(frame.sceneId),
          ).length;
          return {
            id: annotatorId,
            label: annotator?.name ?? annotatorId,
            count: frameCount,
          };
        },
      );
  const maxAllocation = Math.max(1, ...allocationRows.map((row) => row.count));

  const datasetFindingIds = new Set(mockFindings.map((finding) => finding.id));
  const unresolvedComments = state.feedbackComments.filter(
    (comment) =>
      datasetFindingIds.has(comment.findingId) &&
      comment.blocking &&
      !comment.resolved,
  );
  const sourceError = apiSamplesQuery.isError || apiCasesQuery.isError;
  const provenance = apiDataSourceEnabled
    ? "Official · read-only API"
    : "Demo workflow · local fixture";
  const sourceStatus = sourceError
    ? "Source attention"
    : apiSamplesQuery.isPending && apiDataSourceEnabled
      ? "Syncing metadata"
      : "Source available";
  const sourceStatusTone = sourceError
    ? "danger"
    : apiSamplesQuery.isPending && apiDataSourceEnabled
      ? "warning"
      : "success";
  const activeModels = state.models.filter((model) => model.enabled);
  const activeRules = state.rules.filter((rule) => rule.enabled);
  const queueHref = `/qa-cases?dataset=${encodeURIComponent(selectedDatasetId)}`;

  return (
    <div className="page-container view-page dataset-v2">
      <header className="dataset-v2-header">
        <div>
          <h1>Datasets / Runs</h1>
          <p>
            {selectedDatasetName} · {selectedVersion}
          </p>
        </div>
        <div
          className="dataset-v2-header-status"
          aria-label="Dataset source status"
        >
          <span
            className={`dataset-v2-status dataset-v2-status-${sourceStatusTone}`}
          >
            {sourceError ? (
              <AlertTriangle aria-hidden="true" />
            ) : (
              <CheckCircle2 aria-hidden="true" />
            )}
            {sourceStatus}
          </span>
          <span className="dataset-v2-provenance">
            <Database aria-hidden="true" />
            {provenance}
          </span>
        </div>
      </header>

      <div className="dataset-v2-mobile-notice" role="note">
        <HardDrive aria-hidden="true" />
        <div>
          <strong>Optimized for desktop</strong>
          <span>
            Use a desktop to manage runs and inspect frame coverage. Dataset
            status remains available here.
          </span>
        </div>
      </div>

      <div className="dataset-v2-layout">
        <aside className="dataset-v2-catalog" aria-label="Dataset versions">
          <div className="dataset-v2-panel-heading">
            <div>
              <h2>Dataset versions</h2>
              <span>
                {apiDataSourceEnabled ? 1 : state.datasets.length} available
              </span>
            </div>
            <Layers3 aria-hidden="true" />
          </div>

          <div className="dataset-v2-dataset-list">
            {(apiDataSourceEnabled ? cloudDatasets : state.datasets).map(
              (dataset) => {
                const isSelected = dataset.id === selectedDatasetId;
                const batch = state.batches.find(
                  (item) => item.datasetId === dataset.id,
                );
                return (
                  <button
                    className="dataset-v2-dataset-row"
                    type="button"
                    key={dataset.id}
                    aria-current={isSelected ? "true" : undefined}
                    onClick={() => {
                      if (!apiDataSourceEnabled) actions.setDataset(dataset.id);
                    }}
                    disabled={apiDataSourceEnabled}
                  >
                    <span className="dataset-v2-dataset-icon">
                      <Database aria-hidden="true" />
                    </span>
                    <span className="dataset-v2-dataset-copy">
                      <strong>{dataset.name}</strong>
                      <small>
                        {dataset.version} · {dataset.format}
                      </small>
                      <span>
                        <i
                          className={`dataset-v2-source-dot ${apiDataSourceEnabled ? "is-official" : "is-demo"}`}
                        />
                        {apiDataSourceEnabled
                          ? "Official"
                          : (batch?.state ?? "Fixture")}
                      </span>
                    </span>
                    {isSelected ? <Check aria-label="Selected" /> : null}
                  </button>
                );
              },
            )}
          </div>

          <dl className="dataset-v2-catalog-meta">
            <div>
              <dt>Scope</dt>
              <dd>{activeSplit}</dd>
            </div>
            <div>
              <dt>Format</dt>
              <dd>{selectedFormat}</dd>
            </div>
            <div>
              <dt>Privacy</dt>
              <dd>
                {apiDataSourceEnabled || selectedDataset.anonymized
                  ? "Protected"
                  : "Review"}
              </dd>
            </div>
          </dl>
        </aside>

        <main className="dataset-v2-control-plane">
          <section
            className="dataset-v2-lifecycle"
            aria-labelledby="dataset-lifecycle-title"
          >
            <div className="dataset-v2-section-heading">
              <div>
                <h2 id="dataset-lifecycle-title">Dataset lifecycle</h2>
                <p>Current operational state from intake to release.</p>
              </div>
              <span className="dataset-v2-context-chip">
                <Workflow aria-hidden="true" />
                {apiDataSourceEnabled ? "API scope" : "Fixture state"}
              </span>
            </div>
            <ol className="dataset-v2-stage-rail">
              {lifecycle.map((stage) => {
                const StageIcon = stage.icon;
                return (
                  <li
                    className={`dataset-v2-stage is-${stage.state}`}
                    key={stage.id}
                  >
                    <div className="dataset-v2-stage-node">
                      <StageIcon aria-hidden="true" />
                    </div>
                    <div className="dataset-v2-stage-copy">
                      <strong>{stage.label}</strong>
                      <span>{stage.detail}</span>
                    </div>
                    <span className="dataset-v2-stage-marker">
                      <StageMarker state={stage.state} />
                    </span>
                  </li>
                );
              })}
            </ol>
          </section>

          <div className="dataset-v2-workspace-grid">
            <section
              className="dataset-v2-coverage"
              aria-labelledby="dataset-coverage-title"
            >
              <div className="dataset-v2-section-heading">
                <div>
                  <h2 id="dataset-coverage-title">Frame coverage</h2>
                  <p>
                    {apiDataSourceEnabled
                      ? "Loaded page scope; total dataset coverage is not exposed."
                      : "Evaluation coverage across fixture scenes."}
                  </p>
                </div>
                <div className="dataset-v2-coverage-total">
                  <strong>
                    {apiDataSourceEnabled
                      ? (apiSamples?.count ?? 0)
                      : `${percent(run.processedFrames, run.totalFrames)}%`}
                  </strong>
                  <span>
                    {apiDataSourceEnabled
                      ? "samples loaded"
                      : `${run.processedFrames}/${run.totalFrames} frames`}
                  </span>
                </div>
              </div>

              <div className="dataset-v2-coverage-body">
                <figure className="dataset-v2-frame-preview">
                  {previewImage ? (
                    <img
                      src={previewImage}
                      alt={`Dataset preview for ${previewLabel}`}
                    />
                  ) : (
                    <div className="dataset-v2-preview-empty">
                      <ScanSearch aria-hidden="true" />
                      <span>No frame preview</span>
                    </div>
                  )}
                  <figcaption>
                    <span>{previewLabel}</span>
                    <small>
                      {apiDataSourceEnabled
                        ? "Official frame sample"
                        : "Demo fixture preview"}
                    </small>
                  </figcaption>
                </figure>

                <div
                  className="dataset-v2-coverage-map"
                  aria-label="Coverage by sequence"
                >
                  {coverageRows.length ? (
                    coverageRows.map((row) => (
                      <div className="dataset-v2-coverage-row" key={row.id}>
                        <div>
                          <strong>{row.name}</strong>
                          <span>{row.meta}</span>
                        </div>
                        <div className="dataset-v2-frame-cells">
                          {row.cells.map((cell, index) => (
                            <i
                              className={`is-${cell}`}
                              title={`${row.name} · item ${index + 1} · ${cell}`}
                              key={`${row.id}-${index}`}
                            />
                          ))}
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="dataset-v2-inline-empty">
                      <CircleDashed aria-hidden="true" />
                      <span>
                        {apiSamplesQuery.isPending
                          ? "Loading sequence metadata"
                          : "No frame samples in this scope"}
                      </span>
                    </div>
                  )}
                  <div
                    className="dataset-v2-map-legend"
                    aria-label="Coverage legend"
                  >
                    <span>
                      <i className="is-ready" />
                      Available
                    </span>
                    {!apiDataSourceEnabled ? (
                      <span>
                        <i className="is-processed" />
                        Processed
                      </span>
                    ) : null}
                    {!apiDataSourceEnabled ? (
                      <span>
                        <i className="is-flagged" />
                        Flagged
                      </span>
                    ) : null}
                  </div>
                </div>
              </div>
            </section>

            <section
              className="dataset-v2-allocation"
              aria-labelledby="dataset-allocation-title"
            >
              <div className="dataset-v2-section-heading">
                <div>
                  <h2 id="dataset-allocation-title">Workload allocation</h2>
                  <p>
                    {apiDataSourceEnabled
                      ? "Assignment telemetry is not exposed by this API."
                      : "Scene scope from the demo fixture, not production assignment."}
                  </p>
                </div>
                <UsersRound aria-hidden="true" />
              </div>
              {allocationRows.length ? (
                <div className="dataset-v2-allocation-list">
                  {allocationRows.map((row) => (
                    <div className="dataset-v2-allocation-row" key={row.id}>
                      <div>
                        <strong>{row.label}</strong>
                        <span>{row.count} fixture frames</span>
                      </div>
                      <div className="dataset-v2-allocation-track">
                        <i
                          style={{
                            width: `${percent(row.count, maxAllocation)}%`,
                          }}
                        />
                      </div>
                    </div>
                  ))}
                  <span className="dataset-v2-truth-label">
                    <LockKeyhole aria-hidden="true" />
                    Demo workflow
                  </span>
                </div>
              ) : (
                <div className="dataset-v2-not-tracked">
                  <UsersRound aria-hidden="true" />
                  <div>
                    <strong>Not tracked</strong>
                    <span>
                      Connect the assignment API to show owners and workload
                      balance.
                    </span>
                  </div>
                </div>
              )}
            </section>

            <section
              className="dataset-v2-blockers"
              aria-labelledby="dataset-blockers-title"
            >
              <div className="dataset-v2-section-heading">
                <div>
                  <h2 id="dataset-blockers-title">Blocking issues</h2>
                  <p>
                    Only verified source errors and unresolved blocking
                    feedback.
                  </p>
                </div>
                <span
                  className={`dataset-v2-count ${sourceError || unresolvedComments.length ? "has-attention" : ""}`}
                >
                  {sourceError ? 1 : unresolvedComments.length}
                </span>
              </div>
              <div className="dataset-v2-blocker-list">
                {sourceError ? (
                  <div className="dataset-v2-blocker-row is-error">
                    <AlertTriangle aria-hidden="true" />
                    <div>
                      <strong>Dataset source request failed</strong>
                      <span>
                        Metadata or QA cases could not be loaded for{" "}
                        {apiDataset} · {apiSplit}.
                      </span>
                    </div>
                    <button
                      type="button"
                      onClick={() => {
                        void apiSamplesQuery.refetch();
                        void apiCasesQuery.refetch();
                      }}
                    >
                      <RefreshCcw aria-hidden="true" />
                      <span>Retry</span>
                    </button>
                  </div>
                ) : unresolvedComments.length ? (
                  unresolvedComments.slice(0, 3).map((comment) => {
                    const author = state.users.find(
                      (user) => user.id === comment.authorId,
                    );
                    return (
                      <div className="dataset-v2-blocker-row" key={comment.id}>
                        <AlertTriangle aria-hidden="true" />
                        <div>
                          <strong>
                            {comment.reasonCategory.replace("_", " ")}
                          </strong>
                          <span>
                            {comment.targetType} · revision{" "}
                            {comment.annotationRevision ?? "Not tracked"} ·{" "}
                            {author?.name ?? "Reviewer"}
                          </span>
                        </div>
                        <Link to={queueHref}>
                          Inspect
                          <ArrowUpRight aria-hidden="true" />
                        </Link>
                      </div>
                    );
                  })
                ) : (
                  <div className="dataset-v2-inline-empty is-success">
                    <CheckCircle2 aria-hidden="true" />
                    <span>
                      {apiDataSourceEnabled
                        ? "No source blocker reported. Workflow blockers are not tracked by this API."
                        : "No unresolved blocking feedback in this fixture scope."}
                    </span>
                  </div>
                )}
              </div>
            </section>
          </div>
        </main>

        <aside
          className="dataset-v2-run-drawer"
          aria-label="Selected run context"
        >
          <div className="dataset-v2-panel-heading">
            <div>
              <h2>{roleCopy[activeRole].title}</h2>
              <span>{roleCopy[activeRole].label}</span>
            </div>
            <SlidersHorizontal aria-hidden="true" />
          </div>
          <p className="dataset-v2-role-note">{roleCopy[activeRole].note}</p>

          <div className="dataset-v2-run-status">
            <div className="dataset-v2-run-status-heading">
              <span>{apiDataSourceEnabled ? "Dataset review" : "QA run"}</span>
              <strong>
                {apiDataSourceEnabled
                  ? apiSamplesQuery.isPending
                    ? "Syncing"
                    : "Read only"
                  : run.status === "completed"
                    ? "Completed"
                    : run.status === "running"
                      ? "Running"
                      : "Ready"}
              </strong>
            </div>
            <div
              className="dataset-v2-run-progress"
              role="progressbar"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={
                apiDataSourceEnabled
                  ? percent(reviewedCases, apiCases.length)
                  : run.progress
              }
            >
              <i
                style={{
                  width: `${apiDataSourceEnabled ? percent(reviewedCases, apiCases.length) : run.progress}%`,
                }}
              />
            </div>
            <div className="dataset-v2-run-figures">
              <div>
                <strong>
                  {apiDataSourceEnabled ? reviewedCases : run.processedFrames}
                </strong>
                <span>
                  {apiDataSourceEnabled ? "reviewed cases" : "processed frames"}
                </span>
              </div>
              <div>
                <strong>
                  {apiDataSourceEnabled ? highRiskCases : mockFindings.length}
                </strong>
                <span>
                  {apiDataSourceEnabled ? "high risk" : "fixture findings"}
                </span>
              </div>
            </div>
          </div>

          <div className="dataset-v2-role-actions">
            {activeRole === "admin" && !apiDataSourceEnabled ? (
              run.status === "running" ? (
                <Button variant="primary" onClick={actions.advanceQaRun}>
                  <Play aria-hidden="true" />
                  Advance run
                </Button>
              ) : (
                <Button
                  variant="primary"
                  onClick={() => actions.startQaRun(selectedDataset.id)}
                >
                  <Play aria-hidden="true" />
                  {run.status === "completed" ? "Run again" : "Start demo run"}
                </Button>
              )
            ) : activeRole === "admin" ? (
              <Button
                variant="secondary"
                disabled
                title="The current API is read-only and does not expose run creation"
              >
                <LockKeyhole aria-hidden="true" />
                Run unavailable
              </Button>
            ) : (
              <Link className="dataset-v2-primary-link" to={queueHref}>
                {activeRole === "reviewer"
                  ? "Inspect QA cases"
                  : "View assigned scope"}
                <ArrowUpRight aria-hidden="true" />
              </Link>
            )}
            {!apiDataSourceEnabled &&
            activeRole === "admin" &&
            run.status === "running" ? (
              <span>Demo advances in 25% steps.</span>
            ) : null}
          </div>

          <dl className="dataset-v2-run-meta">
            <div>
              <dt>Run ID</dt>
              <dd>{apiDataSourceEnabled ? "Not exposed" : run.id}</dd>
            </div>
            <div>
              <dt>Started</dt>
              <dd>
                {apiDataSourceEnabled
                  ? "Not exposed"
                  : displayTime(run.startedAt)}
              </dd>
            </div>
            <div>
              <dt>Duration</dt>
              <dd>
                {apiDataSourceEnabled
                  ? "Not exposed"
                  : run.durationSeconds
                    ? `${run.durationSeconds}s`
                    : "Not available"}
              </dd>
            </div>
            <div>
              <dt>Model</dt>
              <dd>
                {apiDataSourceEnabled
                  ? "Not exposed"
                  : run.modelVersion ||
                    activeModels.map((model) => model.version).join(", ") ||
                    "No model enabled"}
              </dd>
            </div>
            <div>
              <dt>Rules</dt>
              <dd>
                {apiDataSourceEnabled
                  ? "Not exposed"
                  : run.ruleVersion || `${activeRules.length} enabled`}
              </dd>
            </div>
          </dl>

          <section
            className="dataset-v2-delta"
            aria-labelledby="run-delta-title"
          >
            <div>
              <GitCompareArrows aria-hidden="true" />
              <h3 id="run-delta-title">Run delta</h3>
            </div>
            <dl>
              <div>
                <dt>Pass rate</dt>
                <dd>Not tracked</dd>
              </div>
              <div>
                <dt>Risk cases</dt>
                <dd>Not tracked</dd>
              </div>
              <div>
                <dt>Processing errors</dt>
                <dd>{sourceError ? "Source error" : "Not tracked"}</dd>
              </div>
            </dl>
            <p>
              No previous run comparison is available in the current contract.
            </p>
          </section>

          <div className="dataset-v2-truth-note">
            <LockKeyhole aria-hidden="true" />
            <div>
              <strong>
                {apiDataSourceEnabled ? "Production truth" : "Fixture truth"}
              </strong>
              <span>
                {apiDataSourceEnabled
                  ? "Official source is read-only. Batch, assignment and release telemetry are not exposed."
                  : "Run progress and workflow counts are local demo fixtures; no model inference or backend write occurs."}
              </span>
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}
