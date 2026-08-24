import { useEffect, useMemo, useState, type FormEvent } from "react";
import { CheckCircle2, CircleDot, RefreshCw, Send, ShieldAlert } from "lucide-react";
import { labelGuardianApiV1 } from "../api/labelGuardianApi";
import type { PipelineRunDto } from "../api/types";
import { Badge, Button, Card, SectionHeading, StatCard } from "../components/ui";

const phaseLabels: Record<string, string> = {
  acquire_raw: "Download raw",
  normalize: "Normalize",
  validate: "Validate",
  publish: "Publish",
};

function displayTime(value: string | null | undefined) {
  return value ? new Date(value).toLocaleString("vi-VN") : "—";
}

function statusTone(status: string): "success" | "info" | "high" | "neutral" {
  if (status === "completed") return "success";
  if (status === "running" || status === "submitted") return "info";
  if (status === "failed" || status === "blocked_credentials") return "high";
  return "neutral";
}

function pipelineHealth(run: PipelineRunDto | null) {
  if (!run) return { active: "—", images: 0, objects: 0, stage: "—" };
  const activeStage = run.stages.find((stage) => stage.percent < 100)?.phase ?? "completed";
  return {
    active: run.status,
    images: run.images,
    objects: run.objects,
    stage: activeStage === "completed" ? "Published" : (phaseLabels[activeStage] ?? activeStage),
  };
}

export function PipelineView() {
  const [runs, setRuns] = useState<PipelineRunDto[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string>("");
  const [selectedRun, setSelectedRun] = useState<PipelineRunDto | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitMessage, setSubmitMessage] = useState<string | null>(null);
  const [datasetType, setDatasetType] = useState<"kitti" | "nuscenes">("kitti");
  const [runId, setRunId] = useState("");
  const [maxFrames, setMaxFrames] = useState(5);
  const [urls, setUrls] = useState({ image2: "", label2: "", calib: "", velodyne: "", nuscenes: "" });
  const health = useMemo(() => pipelineHealth(selectedRun), [selectedRun]);

  const refreshRuns = async (signal?: AbortSignal) => {
    setLoading(true);
    setError(null);
    try {
      const list = await labelGuardianApiV1.listPipelineRuns(signal);
      setRuns(list.results);
      const nextRunId = selectedRunId || list.results[0]?.runId || "";
      setSelectedRunId(nextRunId);
      if (nextRunId) {
        setSelectedRun(await labelGuardianApiV1.getPipelineRun(nextRunId, signal));
      } else {
        setSelectedRun(null);
      }
    } catch (caught) {
      if (!signal?.aborted) setError(caught instanceof Error ? caught.message : "Pipeline API error");
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  };

  useEffect(() => {
    const controller = new AbortController();
    void refreshRuns(controller.signal);
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!selectedRunId) return;
    const controller = new AbortController();
    void labelGuardianApiV1.getPipelineRun(selectedRunId, controller.signal).then(setSelectedRun).catch((caught) => {
      if (!controller.signal.aborted) setError(caught instanceof Error ? caught.message : "Pipeline API error");
    });
    const timer = window.setInterval(() => {
      void labelGuardianApiV1.getPipelineRun(selectedRunId, controller.signal).then(setSelectedRun).catch(() => undefined);
    }, 8000);
    return () => {
      controller.abort();
      window.clearInterval(timer);
    };
  }, [selectedRunId]);

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmitMessage(
      "Cloud trigger UI đã nhận cấu hình. Backend control endpoint đang khóa để tránh ghi Secret Manager và tạo Cloud Batch job ngoài ý muốn.",
    );
  };

  return (
    <div className="page-container view-page pipeline-page">
      <div className="page-heading">
        <div>
          <span className="eyebrow">Cloud dataset pipeline</span>
          <h1>Pipeline</h1>
          <p className="page-description">Theo dõi ingestion runs, stage progress, validation output và cloud worker logs.</p>
        </div>
        <div className="page-heading-actions">
          <Button variant="secondary" onClick={() => void refreshRuns()} disabled={loading}>
            <RefreshCw size={15} /> Refresh
          </Button>
          {selectedRun ? <Badge tone={statusTone(selectedRun.status)}>{selectedRun.status}</Badge> : null}
        </div>
      </div>

      {error ? <Card className="pipeline-alert"><ShieldAlert size={18} /><span>{error}</span></Card> : null}
      {submitMessage ? <Card className="pipeline-notice"><CircleDot size={18} /><span>{submitMessage}</span></Card> : null}

      <section className="dataset-run-kpi-grid">
        <StatCard label="Active run" value={selectedRun?.runId ?? "—"} detail={health.active} tone="blue" />
        <StatCard label="Current stage" value={health.stage} detail={selectedRun?.datasetType ?? "dataset"} tone="purple" />
        <StatCard label="Images" value={health.images} detail={selectedRun?.canonicalPrefix ?? "canonical prefix"} tone="green" />
        <StatCard label="Objects" value={health.objects} detail={selectedRun?.split ?? "split"} tone="orange" />
      </section>

      <div className="pipeline-grid">
        <Card className="pipeline-runs-card">
          <SectionHeading eyebrow="Runs" title="Cloud executions" />
          <div className="pipeline-run-list">
            {runs.map((run) => (
              <button
                className={`pipeline-run-row ${run.runId === selectedRunId ? "is-active" : ""}`}
                key={run.runId}
                type="button"
                onClick={() => setSelectedRunId(run.runId)}
              >
                <span>
                  <strong>{run.runId}</strong>
                  <small>{run.datasetType} · {run.release ?? "release"} · {run.split ?? "split"}</small>
                </span>
                <Badge tone={statusTone(run.status)}>{run.status}</Badge>
              </button>
            ))}
            {!runs.length ? <div className="pipeline-empty">No ingestion runs</div> : null}
          </div>
        </Card>

        <Card className="pipeline-control-card">
          <SectionHeading eyebrow="Trigger" title="Dataset source" />
          <div className="pipeline-control-lock">
            <ShieldAlert size={15} />
            <span>Submit thật cần backend control token, audit và cost guard. Form này đang chuẩn bị cấu hình để nối endpoint admin sau.</span>
          </div>
          <form className="pipeline-trigger-form" onSubmit={handleSubmit}>
            <div className="pipeline-form-row">
              <label>
                <span>Dataset</span>
                <select value={datasetType} onChange={(event) => setDatasetType(event.target.value as "kitti" | "nuscenes")}>
                  <option value="kitti">KITTI</option>
                  <option value="nuscenes">nuScenes</option>
                </select>
              </label>
              <label>
                <span>Max frames</span>
                <input type="number" min={1} max={100} value={maxFrames} onChange={(event) => setMaxFrames(Number(event.target.value))} />
              </label>
            </div>
            <label>
              <span>Run ID</span>
              <input value={runId} onChange={(event) => setRunId(event.target.value)} placeholder={`${datasetType}-smoke-next`} />
            </label>
            {datasetType === "kitti" ? (
              <>
                <input value={urls.image2} onChange={(event) => setUrls({ ...urls, image2: event.target.value })} placeholder="data_object_image_2.zip URL" />
                <input value={urls.label2} onChange={(event) => setUrls({ ...urls, label2: event.target.value })} placeholder="data_object_label_2.zip URL" />
                <input value={urls.calib} onChange={(event) => setUrls({ ...urls, calib: event.target.value })} placeholder="data_object_calib.zip URL" />
                <input value={urls.velodyne} onChange={(event) => setUrls({ ...urls, velodyne: event.target.value })} placeholder="data_object_velodyne.zip URL" />
              </>
            ) : (
              <input value={urls.nuscenes} onChange={(event) => setUrls({ ...urls, nuscenes: event.target.value })} placeholder="v1.0-mini.tgz URL" />
            )}
            <Button variant="primary" type="submit">
              <Send size={15} /> Prepare cloud run
            </Button>
          </form>
        </Card>
      </div>

      <div className="pipeline-detail-grid">
        <Card className="pipeline-stage-card">
          <SectionHeading eyebrow="Progress" title={selectedRun?.batchJobId ?? "No batch job selected"} />
          <div className="pipeline-flow" aria-label="Pipeline stage graph">
            {(selectedRun?.stages ?? []).map((stage, index, stages) => {
              const completed = stage.percent >= 100;
              const active = !completed && stages.slice(0, index).every((item) => item.percent >= 100);
              return (
                <div className={`pipeline-flow-node ${completed ? "is-complete" : ""} ${active ? "is-active" : ""}`} key={stage.phase}>
                  <div className="pipeline-flow-marker">
                    {completed ? <CheckCircle2 size={16} /> : <CircleDot size={16} />}
                  </div>
                  <strong>{phaseLabels[stage.phase] ?? stage.phase}</strong>
                  <span>{stage.percent}%</span>
                </div>
              );
            })}
          </div>
          <div className="pipeline-stage-list">
            {(selectedRun?.stages ?? []).map((stage) => (
              <div className="pipeline-stage-row" key={stage.phase}>
                <div>
                  <strong>{phaseLabels[stage.phase] ?? stage.phase}</strong>
                  <span>{stage.detail}</span>
                </div>
                <span>{stage.percent}%</span>
                <div className="progress-track"><div className="progress-fill progress-blue" style={{ width: `${stage.percent}%` }} /></div>
              </div>
            ))}
          </div>
        </Card>

        <Card className="pipeline-events-card">
          <SectionHeading eyebrow="Events" title="Worker state" />
          <div className="pipeline-event-list">
            {(selectedRun?.events ?? []).map((event, index) => (
              <div className="pipeline-event-row" key={`${event.createdAt}-${index}`}>
                <span className={`pipeline-event-dot status-${event.status}`} />
                <div>
                  <strong>{event.phase} · {event.status}</strong>
                  <p>{event.message}</p>
                  <small>{displayTime(event.createdAt)}</small>
                </div>
              </div>
            ))}
            {!selectedRun?.events.length ? <div className="pipeline-empty">No worker events</div> : null}
          </div>
        </Card>
      </div>

      <Card className="pipeline-log-card">
        <SectionHeading eyebrow="Logs" title="Cloud Batch stage output" />
        <div className="pipeline-log-console">
          {(selectedRun?.logs ?? []).map((log, index) => (
            <div key={`${log.timestamp ?? "log"}-${index}`}>
              <span>{log.timestamp ? displayTime(log.timestamp) : "—"}</span>
              <code>{log.message}</code>
            </div>
          ))}
          {!selectedRun?.logs.length ? <div className="pipeline-empty">No logs linked to this run</div> : null}
        </div>
      </Card>
    </div>
  );
}
