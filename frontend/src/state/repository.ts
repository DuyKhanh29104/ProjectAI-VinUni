import type {
  AnnotationRecord,
  MockState,
  ModelConfig,
  ReviewAction,
  ReviewStatus,
  Role,
  RuleConfig,
} from "../domain/types.ts";

export type AnnotationChanges = Partial<
  Pick<AnnotationRecord, "label" | "bbox" | "trackId" | "attributes">
>;

/**
 * Synchronous state adapter used by the current mock reducer.
 * The UI depends on this contract instead of importing MockRepository directly.
 */
export interface LabelGuardianRepository {
  seed(): MockState;
  setActiveRole(state: MockState, role: Role): MockState;
  setSelectedDataset(state: MockState, datasetId: string): MockState;
  startQaRun(state: MockState, datasetId: string): MockState;
  advanceQaRun(state: MockState): MockState;
  updateRule(
    state: MockState,
    ruleId: string,
    changes: Partial<Pick<RuleConfig, "enabled" | "threshold">>,
  ): MockState;
  updateModel(
    state: MockState,
    modelId: string,
    changes: Partial<Pick<ModelConfig, "enabled" | "confidenceThreshold">>,
  ): MockState;
  setFindingStatus(
    state: MockState,
    findingId: string,
    toStatus: ReviewStatus,
    userId: string,
    action: ReviewAction,
    reason?: string,
  ): MockState;
  saveProposedAnnotation(
    state: MockState,
    annotationId: string,
    changes: AnnotationChanges,
    userId: string,
  ): MockState;
  createProposedAnnotation(
    state: MockState,
    findingId: string,
    changes: AnnotationChanges,
    userId: string,
  ): MockState;
  approveFinding(
    state: MockState,
    findingId: string,
    userId: string,
    reason?: string,
  ): MockState;
  addFindingFeedback(
    state: MockState,
    findingId: string,
    userId: string,
    feedback: string,
  ): MockState;
  assignFinding(
    state: MockState,
    findingId: string,
    assigneeId: string,
    userId: string,
  ): MockState;
  reset(): MockState;
}

/** API DTO boundary reserved for the future backend adapter. */
export interface ApiRequestContext {
  baseUrl: string;
  accessToken?: string;
}
