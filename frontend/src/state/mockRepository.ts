import { createInitialMockState } from "../data/mockData.ts";
import type {
  MockState,
  ModelConfig,
  ReviewAction,
  ReviewStatus,
  Role,
  RuleConfig,
} from "../domain/types.ts";
import { MockConfigurationOperations } from "./mock/configurationOperations.ts";
import { MockReviewOperations } from "./mock/reviewOperations.ts";
import type { AnnotationChanges, LabelGuardianRepository } from "./repository.ts";

/**
 * Mock adapter facade. Dataset/configuration transitions and review transitions
 * live in separate modules so adding mock workflows does not grow one monolith.
 */
export class MockRepository implements LabelGuardianRepository {
  private readonly configuration = new MockConfigurationOperations();
  private readonly review = new MockReviewOperations();

  seed(): MockState {
    return createInitialMockState();
  }

  setActiveRole(state: MockState, role: Role): MockState {
    return this.configuration.setActiveRole(state, role);
  }

  setSelectedDataset(state: MockState, datasetId: string): MockState {
    return this.configuration.setSelectedDataset(state, datasetId);
  }

  startQaRun(state: MockState, datasetId: string): MockState {
    return this.configuration.startQaRun(state, datasetId);
  }

  advanceQaRun(state: MockState): MockState {
    return this.configuration.advanceQaRun(state);
  }

  updateRule(
    state: MockState,
    ruleId: string,
    changes: Partial<Pick<RuleConfig, "enabled" | "threshold">>,
  ): MockState {
    return this.configuration.updateRule(state, ruleId, changes);
  }

  updateModel(
    state: MockState,
    modelId: string,
    changes: Partial<Pick<ModelConfig, "enabled" | "confidenceThreshold">>,
  ): MockState {
    return this.configuration.updateModel(state, modelId, changes);
  }

  setFindingStatus(
    state: MockState,
    findingId: string,
    toStatus: ReviewStatus,
    userId: string,
    action: ReviewAction,
    reason?: string,
  ): MockState {
    return this.review.setFindingStatus(state, findingId, toStatus, userId, action, reason);
  }

  saveProposedAnnotation(
    state: MockState,
    annotationId: string,
    changes: AnnotationChanges,
    userId: string,
  ): MockState {
    return this.review.saveProposedAnnotation(state, annotationId, changes, userId);
  }

  createProposedAnnotation(
    state: MockState,
    findingId: string,
    changes: AnnotationChanges,
    userId: string,
  ): MockState {
    return this.review.createProposedAnnotation(state, findingId, changes, userId);
  }

  approveFinding(
    state: MockState,
    findingId: string,
    userId: string,
    reason?: string,
  ): MockState {
    return this.review.approveFinding(state, findingId, userId, reason);
  }

  addFindingFeedback(
    state: MockState,
    findingId: string,
    userId: string,
    feedback: string,
  ): MockState {
    return this.review.addFindingFeedback(state, findingId, userId, feedback);
  }

  assignFinding(
    state: MockState,
    findingId: string,
    assigneeId: string,
    userId: string,
  ): MockState {
    return this.review.assignFinding(state, findingId, assigneeId, userId);
  }

  reset(): MockState {
    return createInitialMockState();
  }
}

export type { AnnotationChanges } from "./repository.ts";
