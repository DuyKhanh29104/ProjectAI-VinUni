import type { MockState } from "../domain/types.ts";
import { mockAnnotations, mockEvidences, mockFindings, mockPredictions } from "./mock/review.ts";
import { mockDatasets, mockFrames, mockScenes } from "./mock/catalog.ts";
import { mockTimestamp } from "./mock/constants.ts";
import { mockModels, mockQaRun, mockReportMetrics, mockRules, mockUsers } from "./mock/workflow.ts";

export function createInitialMockState(): MockState {
  const seed: MockState = {
    datasets: mockDatasets,
    scenes: mockScenes,
    frames: mockFrames,
    annotations: mockAnnotations,
    predictions: mockPredictions,
    evidences: mockEvidences,
    findings: mockFindings,
    reviewDecisions: [],
    users: mockUsers,
    reportMetrics: mockReportMetrics,
    qaRun: mockQaRun,
    rules: mockRules,
    models: mockModels,
    activeRole: "reviewer",
    activeUserId: "user-reviewer",
    selectedDatasetId: "dataset-kitti-demo",
    lastUpdatedAt: mockTimestamp,
  };
  return JSON.parse(JSON.stringify(seed)) as MockState;
}
