import type {
  MockState,
  ModelConfig,
  ReviewAction,
  ReviewStatus,
  Role,
  RuleConfig,
} from "../domain/types.ts";
import type {
  AnnotationChanges,
  ApiRequestContext,
  LabelGuardianRepository,
} from "./repository.ts";

/**
 * Production adapter placeholder. It implements the same contract as MockRepository so the UI
 * boundary is explicit, but intentionally fails fast until the backend/query layer exists.
 */
export class ApiRepository implements LabelGuardianRepository {
  constructor(private readonly context: ApiRequestContext) {}

  seed(): MockState {
    return this.notConfigured();
  }

  setActiveRole(_state: MockState, _role: Role): MockState {
    return this.notConfigured();
  }

  setSelectedDataset(_state: MockState, _datasetId: string): MockState {
    return this.notConfigured();
  }

  startQaRun(_state: MockState, _datasetId: string): MockState {
    return this.notConfigured();
  }

  advanceQaRun(_state: MockState): MockState {
    return this.notConfigured();
  }

  updateRule(
    _state: MockState,
    _ruleId: string,
    _changes: Partial<Pick<RuleConfig, "enabled" | "threshold">>,
  ): MockState {
    return this.notConfigured();
  }

  updateModel(
    _state: MockState,
    _modelId: string,
    _changes: Partial<Pick<ModelConfig, "enabled" | "confidenceThreshold">>,
  ): MockState {
    return this.notConfigured();
  }

  setFindingStatus(
    _state: MockState,
    _findingId: string,
    _toStatus: ReviewStatus,
    _userId: string,
    _action: ReviewAction,
    _reason?: string,
  ): MockState {
    return this.notConfigured();
  }

  saveProposedAnnotation(
    _state: MockState,
    _annotationId: string,
    _changes: AnnotationChanges,
    _userId: string,
  ): MockState {
    return this.notConfigured();
  }

  createProposedAnnotation(
    _state: MockState,
    _findingId: string,
    _changes: AnnotationChanges,
    _userId: string,
  ): MockState {
    return this.notConfigured();
  }

  approveFinding(
    _state: MockState,
    _findingId: string,
    _userId: string,
    _reason?: string,
  ): MockState {
    return this.notConfigured();
  }

  addFindingFeedback(
    _state: MockState,
    _findingId: string,
    _userId: string,
    _feedback: string,
  ): MockState {
    return this.notConfigured();
  }

  assignFinding(
    _state: MockState,
    _findingId: string,
    _assigneeId: string,
    _userId: string,
  ): MockState {
    return this.notConfigured();
  }

  reset(): MockState {
    return this.notConfigured();
  }

  private notConfigured(): never {
    throw new Error(
      `ApiRepository chưa được kết nối. Backend dự kiến tại ${this.context.baseUrl}.`,
    );
  }
}
