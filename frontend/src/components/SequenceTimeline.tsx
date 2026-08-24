import { useMemo } from "react";
import { Badge } from "./ui";
import type { Finding, MockState } from "../domain/types";

interface SequenceTimelineProps {
  state: MockState;
  finding: Finding;
  selectedFrameId: string;
  onFrameChange: (frameId: string) => void;
}

export function SequenceTimeline({
  state,
  finding,
  selectedFrameId,
  onFrameChange,
}: SequenceTimelineProps) {
  const sequenceFrames = useMemo(
    () =>
      state.frames
        .filter((frame) => frame.sceneId === finding.sceneId)
        .sort((first, second) => first.frameNumber - second.frameNumber),
    [finding.sceneId, state.frames],
  );
  const sequenceFindings = state.findings.filter((item) => item.sceneId === finding.sceneId);
  const trackId = finding.trackId;
  const trackAnnotations = state.annotations
    .filter((annotation) => annotation.trackId === trackId && annotation.layer === "original")
    .sort((first, second) => {
      const firstFrame = state.frames.find((frame) => frame.id === first.frameId)?.frameNumber ?? 0;
      const secondFrame = state.frames.find((frame) => frame.id === second.frameId)?.frameNumber ?? 0;
      return firstFrame - secondFrame;
    });

  return (
    <div className="sequence-timeline">
      <div className="sequence-header">
        <div>
          <span className="eyebrow">Temporal context</span>
          <h3>{state.scenes.find((scene) => scene.id === finding.sceneId)?.name ?? finding.sceneId}</h3>
        </div>
        <Badge tone="info">{sequenceFrames.length} frames</Badge>
      </div>

      <div className="timeline-strip" role="list" aria-label="Các frame trong sequence">
        {sequenceFrames.map((frame) => {
          const frameFinding = sequenceFindings.find((item) => item.frameId === frame.id);
          return (
            <button
              className={`timeline-frame ${selectedFrameId === frame.id ? "is-active" : ""} ${frameFinding ? "has-finding" : ""}`}
              key={frame.id}
              type="button"
              onClick={() => onFrameChange(frame.id)}
            >
              <span className="timeline-thumb-wrap">
                <img src={frame.thumbnailUrl} alt="" />
                {frameFinding ? <span className={`timeline-alert alert-${frameFinding.severity}`} /> : null}
              </span>
              <span>F{frame.frameNumber}</span>
            </button>
          );
        })}
      </div>

      <div className="track-overview">
        <div className="track-overview-header">
          <span className="eyebrow">Track continuity</span>
          <strong>{trackId ?? "No track ID"}</strong>
        </div>
        <div className="track-line">
          {sequenceFrames.map((frame) => {
            const annotation = trackAnnotations.find((item) => item.frameId === frame.id);
            const frameFinding = sequenceFindings.find((item) => item.frameId === frame.id && item.trackId === trackId);
            return (
              <button
                className={`track-node ${annotation ? "has-annotation" : "is-missing"} ${frameFinding ? "has-alert" : ""}`}
                key={frame.id}
                type="button"
                onClick={() => onFrameChange(frame.id)}
                title={`Frame ${frame.frameNumber}`}
              >
                <span />
                <small>F{frame.frameNumber}</small>
              </button>
            );
          })}
        </div>
        <div className="track-legend">
          <span><i className="track-dot track-dot-present" /> Có annotation</span>
          <span><i className="track-dot track-dot-missing" /> Không có annotation</span>
          <span><i className="track-dot track-dot-alert" /> Có cảnh báo</span>
        </div>
      </div>
    </div>
  );
}
