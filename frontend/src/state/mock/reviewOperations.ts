import type {
  AnnotationRecord,
  FeedbackComment,
  MockState,
  ReviewAction,
  ReviewStatus,
} from "../../domain/types.ts";
import type { AnnotationChanges } from "../repository.ts";

const now = () => new Date().toISOString();

export class MockReviewOperations {
  setFindingStatus(
    state: MockState,
    findingId: string,
    toStatus: ReviewStatus,
    userId: string,
    action: ReviewAction,
    reason?: string,
  ): MockState {
    const finding = state.findings.find((item) => item.id === findingId);
    if (!finding || finding.status === toStatus) {
      return state;
    }

    const timestamp = now();
    return {
      ...state,
      findings: state.findings.map((item) =>
        item.id === findingId
          ? {
              ...item,
              status: toStatus,
              workflowStage:
                toStatus === "in_review"
                  ? "in_review"
                  : ["confirmed", "corrected", "rejected"].includes(toStatus)
                    ? "approved"
                    : item.workflowStage,
              outcome:
                toStatus === "confirmed"
                  ? "confirmed_issue"
                  : toStatus === "corrected"
                    ? "corrected"
                    : toStatus === "rejected"
                      ? "false_positive"
                      : toStatus === "skipped"
                        ? "skipped"
                        : item.outcome,
              updatedAt: timestamp,
            }
          : item,
      ),
      reviewDecisions: [
        ...state.reviewDecisions,
        {
          id: `decision-${state.reviewDecisions.length + 1}`,
          findingId,
          action,
          userId,
          timestamp,
          reason,
          fromStatus: finding.status,
          toStatus,
        },
      ],
      lastUpdatedAt: timestamp,
    };
  }

  saveProposedAnnotation(
    state: MockState,
    annotationId: string,
    changes: AnnotationChanges,
    userId: string,
  ): MockState {
    const original = state.annotations.find(
      (item) => item.id === annotationId && item.layer === "original",
    );
    if (!original) {
      return state;
    }

    const existingProposal = state.annotations.find(
      (item) =>
        item.layer === "proposed" && item.sourceAnnotationId === annotationId,
    );
    const timestamp = now();
    const proposed: AnnotationRecord = {
      ...original,
      ...changes,
      id: `${annotationId}::proposed`,
      sourceAnnotationId: annotationId,
      layer: "proposed",
      source: "human",
      version: (existingProposal?.version ?? original.version) + 1,
      updatedAt: timestamp,
      updatedBy: userId,
    };

    const annotations = state.annotations.filter(
      (item) => item.id !== proposed.id,
    );
    const finding = state.findings.find(
      (item) => item.annotationId === annotationId,
    );
    const changeSummary = `${original.label} → ${proposed.label}; box ${original.bbox.x},${original.bbox.y},${original.bbox.width}×${original.bbox.height} → ${proposed.bbox.x},${proposed.bbox.y},${proposed.bbox.width}×${proposed.bbox.height}${proposed.attributes.deleted ? "; marked for deletion" : ""}`;
    return {
      ...state,
      annotations: [...annotations, proposed],
      findings: state.findings.map((item) =>
        item.id === finding?.id ? { ...item, updatedAt: timestamp } : item,
      ),
      reviewDecisions: finding
        ? [
            ...state.reviewDecisions,
            {
              id: `decision-${state.reviewDecisions.length + 1}`,
              findingId: finding.id,
              action: "edit_annotation",
              userId,
              timestamp,
              reason: proposed.attributes.sourceNote,
              changeSummary,
              fromStatus: finding.status,
              toStatus: finding.status,
            },
          ]
        : state.reviewDecisions,
      lastUpdatedAt: timestamp,
    };
  }

  createProposedAnnotation(
    state: MockState,
    findingId: string,
    changes: AnnotationChanges,
    userId: string,
  ): MockState {
    const finding = state.findings.find((item) => item.id === findingId);
    if (!finding) {
      return state;
    }

    const existingProposal = state.annotations.find(
      (item) => item.layer === "proposed" && item.sourceFindingId === findingId,
    );
    const timestamp = now();
    const proposed: AnnotationRecord = {
      id: `${findingId}::proposed`,
      sourceFindingId: findingId,
      frameId: finding.frameId,
      trackId: changes.trackId ?? finding.trackId,
      label: changes.label ?? "car",
      bbox: changes.bbox ?? { x: 0, y: 0, width: 120, height: 120 },
      attributes: changes.attributes ?? {},
      layer: "proposed",
      source: "human",
      version: (existingProposal?.version ?? 0) + 1,
      updatedAt: timestamp,
      updatedBy: userId,
    };
    const annotations = state.annotations.filter(
      (item) => item.id !== proposed.id,
    );
    return {
      ...state,
      annotations: [...annotations, proposed],
      findings: state.findings.map((item) =>
        item.id === findingId ? { ...item, updatedAt: timestamp } : item,
      ),
      reviewDecisions: [
        ...state.reviewDecisions,
        {
          id: `decision-${state.reviewDecisions.length + 1}`,
          findingId,
          action: "edit_annotation",
          userId,
          timestamp,
          reason: proposed.attributes.sourceNote,
          changeSummary: `Missing object → ${proposed.label}; box ${proposed.bbox.x},${proposed.bbox.y},${proposed.bbox.width}×${proposed.bbox.height}`,
          fromStatus: finding.status,
          toStatus: finding.status,
        },
      ],
      lastUpdatedAt: timestamp,
    };
  }

  approveFinding(
    state: MockState,
    findingId: string,
    userId: string,
    reason?: string,
  ): MockState {
    const finding = state.findings.find((item) => item.id === findingId);
    if (!finding) {
      return state;
    }

    const proposal = state.annotations.find(
      (item) =>
        item.layer === "proposed" &&
        ((finding.annotationId &&
          item.sourceAnnotationId === finding.annotationId) ||
          item.sourceFindingId === findingId),
    );
    if (!proposal) {
      return this.setFindingStatus(
        state,
        findingId,
        "confirmed",
        userId,
        "confirm",
        reason,
      );
    }

    const timestamp = now();
    const approved: AnnotationRecord = {
      ...proposal,
      id: `${finding.annotationId ?? finding.id}::approved`,
      sourceAnnotationId: finding.annotationId,
      sourceFindingId: finding.id,
      layer: "approved",
      version: proposal.version + 1,
      updatedAt: timestamp,
      updatedBy: userId,
    };
    const annotations = state.annotations.filter(
      (item) =>
        !(
          item.layer === "approved" &&
          ((finding.annotationId &&
            item.sourceAnnotationId === finding.annotationId) ||
            item.sourceFindingId === findingId)
        ),
    );

    const nextState = this.setFindingStatus(
      {
        ...state,
        annotations: [...annotations, approved],
      },
      findingId,
      "corrected",
      userId,
      "approve_correction",
      reason,
    );

    return { ...nextState, lastUpdatedAt: timestamp };
  }

  addFindingFeedback(
    state: MockState,
    findingId: string,
    userId: string,
    feedback: string,
  ): MockState {
    const finding = state.findings.find((item) => item.id === findingId);
    if (!finding || !feedback.trim()) {
      return state;
    }

    const timestamp = now();
    return {
      ...state,
      reviewDecisions: [
        ...state.reviewDecisions,
        {
          id: `decision-${state.reviewDecisions.length + 1}`,
          findingId,
          action: "annotator_feedback",
          userId,
          timestamp,
          reason: feedback.trim(),
          fromStatus: finding.status,
          toStatus: finding.status,
        },
      ],
      lastUpdatedAt: timestamp,
    };
  }

  assignFinding(
    state: MockState,
    findingId: string,
    assigneeId: string,
    userId: string,
  ): MockState {
    const timestamp = now();
    const finding = state.findings.find((item) => item.id === findingId);
    if (!finding) {
      return state;
    }

    return {
      ...state,
      findings: state.findings.map((item) =>
        item.id === findingId
          ? {
              ...item,
              assigneeId,
              workflowStage:
                item.workflowStage === "unassigned"
                  ? "assigned"
                  : item.workflowStage,
              updatedAt: timestamp,
            }
          : item,
      ),
      reviewDecisions: [
        ...state.reviewDecisions,
        {
          id: `decision-${state.reviewDecisions.length + 1}`,
          findingId,
          action: "assign",
          userId,
          timestamp,
          reason: `Assigned to ${assigneeId}`,
          fromStatus: finding.status,
          toStatus: finding.status,
        },
      ],
      lastUpdatedAt: timestamp,
    };
  }

  requestChanges(
    state: MockState,
    findingId: string,
    userId: string,
    assigneeId: string,
    feedback: string,
    reasonCategory: FeedbackComment["reasonCategory"],
  ): MockState {
    const finding = state.findings.find((item) => item.id === findingId);
    if (!finding || !feedback.trim()) return state;
    const timestamp = now();
    const latestRevision = Math.max(
      1,
      ...state.annotations
        .filter((item) => item.frameId === finding.frameId)
        .map((item) => item.version),
    );
    const comment: FeedbackComment = {
      id: `comment-${state.feedbackComments.length + 1}`,
      findingId,
      authorId: userId,
      targetType: finding.annotationId ? "bbox" : "frame",
      targetId: finding.annotationId ?? finding.frameId,
      annotationRevision: latestRevision,
      reasonCategory,
      body: feedback.trim(),
      blocking: true,
      resolved: false,
      createdAt: timestamp,
    };
    return {
      ...state,
      findings: state.findings.map((item) =>
        item.id === findingId
          ? {
              ...item,
              assigneeId,
              workflowStage: "changes_requested",
              status: "in_review",
              outcome: undefined,
              updatedAt: timestamp,
            }
          : item,
      ),
      feedbackComments: [...state.feedbackComments, comment],
      reviewDecisions: [
        ...state.reviewDecisions,
        {
          id: `decision-${state.reviewDecisions.length + 1}`,
          findingId,
          action: "request_changes",
          userId,
          timestamp,
          reason: feedback.trim(),
          fromStatus: finding.status,
          toStatus: "in_review",
        },
      ],
      lastUpdatedAt: timestamp,
    };
  }

  resubmitFinding(
    state: MockState,
    findingId: string,
    userId: string,
    note?: string,
  ): MockState {
    const finding = state.findings.find((item) => item.id === findingId);
    if (!finding || finding.workflowStage !== "changes_requested") return state;
    const timestamp = now();
    return {
      ...state,
      findings: state.findings.map((item) =>
        item.id === findingId
          ? {
              ...item,
              workflowStage: "resubmitted",
              status: "in_review",
              updatedAt: timestamp,
            }
          : item,
      ),
      feedbackComments: state.feedbackComments.map((comment) =>
        comment.findingId === findingId && comment.blocking && !comment.resolved
          ? {
              ...comment,
              resolved: true,
              resolvedAt: timestamp,
              resolvedBy: userId,
            }
          : comment,
      ),
      reviewDecisions: [
        ...state.reviewDecisions,
        {
          id: `decision-${state.reviewDecisions.length + 1}`,
          findingId,
          action: "resubmit",
          userId,
          timestamp,
          reason: note?.trim() || "Annotation rework submitted",
          fromStatus: finding.status,
          toStatus: "in_review",
        },
      ],
      lastUpdatedAt: timestamp,
    };
  }

  resolveFeedback(
    state: MockState,
    commentId: string,
    userId: string,
  ): MockState {
    const comment = state.feedbackComments.find(
      (item) => item.id === commentId,
    );
    if (!comment || comment.resolved) return state;
    const finding = state.findings.find(
      (item) => item.id === comment.findingId,
    );
    if (!finding) return state;
    const timestamp = now();
    return {
      ...state,
      feedbackComments: state.feedbackComments.map((item) =>
        item.id === commentId
          ? {
              ...item,
              resolved: true,
              resolvedAt: timestamp,
              resolvedBy: userId,
            }
          : item,
      ),
      reviewDecisions: [
        ...state.reviewDecisions,
        {
          id: `decision-${state.reviewDecisions.length + 1}`,
          findingId: finding.id,
          action: "resolve_comment",
          userId,
          timestamp,
          reason: comment.body,
          fromStatus: finding.status,
          toStatus: finding.status,
        },
      ],
      lastUpdatedAt: timestamp,
    };
  }
}
