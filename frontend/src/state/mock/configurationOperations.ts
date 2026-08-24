import type { MockState, ModelConfig, Role, RuleConfig } from "../../domain/types.ts";

const now = () => new Date().toISOString();

const userByRole: Record<Role, string> = {
  reviewer: "user-reviewer",
  annotator: "user-annotator",
  admin: "user-admin",
};

export class MockConfigurationOperations {
  setActiveRole(state: MockState, role: Role): MockState {
    return {
      ...state,
      activeRole: role,
      activeUserId: userByRole[role],
      lastUpdatedAt: now(),
    };
  }

  setSelectedDataset(state: MockState, datasetId: string): MockState {
    const datasetExists = state.datasets.some((dataset) => dataset.id === datasetId);
    if (!datasetExists) {
      return state;
    }

    return {
      ...state,
      selectedDatasetId: datasetId,
      lastUpdatedAt: now(),
    };
  }

  startQaRun(state: MockState, datasetId: string): MockState {
    const dataset = state.datasets.find((item) => item.id === datasetId);
    if (!dataset) {
      return state;
    }

    const totalFrames = state.frames.filter((frame) =>
      state.scenes.some((scene) => scene.id === frame.sceneId && scene.datasetId === datasetId),
    ).length;
    const activeModel = state.models.find((model) => model.enabled) ?? state.models[0];
    const enabledRules = state.rules.filter((rule) => rule.enabled).map((rule) => rule.id).join(" + ");
    const timestamp = now();
    return {
      ...state,
      qaRun: {
        ...state.qaRun,
        id: `qa-run-${Date.now()}`,
        datasetId,
        status: "running",
        progress: 0,
        processedFrames: 0,
        totalFrames,
        startedAt: timestamp,
        completedAt: undefined,
        durationSeconds: undefined,
        modelVersion: activeModel?.version ?? "No model enabled",
        ruleVersion: enabledRules || "No rules enabled",
      },
      lastUpdatedAt: timestamp,
    };
  }

  advanceQaRun(state: MockState): MockState {
    if (state.qaRun.status !== "running") {
      return state;
    }

    const progress = Math.min(100, state.qaRun.progress + 25);
    const processedFrames = Math.min(
      state.qaRun.totalFrames,
      Math.ceil((state.qaRun.totalFrames * progress) / 100),
    );
    const completed = progress >= 100;
    const timestamp = now();
    return {
      ...state,
      qaRun: {
        ...state.qaRun,
        status: completed ? "completed" : "running",
        progress,
        processedFrames,
        completedAt: completed ? timestamp : undefined,
        durationSeconds: completed ? 18 : undefined,
      },
      lastUpdatedAt: timestamp,
    };
  }

  updateRule(
    state: MockState,
    ruleId: string,
    changes: Partial<Pick<RuleConfig, "enabled" | "threshold">>,
  ): MockState {
    if (!state.rules.some((rule) => rule.id === ruleId)) {
      return state;
    }

    return {
      ...state,
      rules: state.rules.map((rule) =>
        rule.id === ruleId ? { ...rule, ...changes } : rule,
      ),
      lastUpdatedAt: now(),
    };
  }

  updateModel(
    state: MockState,
    modelId: string,
    changes: Partial<Pick<ModelConfig, "enabled" | "confidenceThreshold">>,
  ): MockState {
    if (!state.models.some((model) => model.id === modelId)) {
      return state;
    }

    return {
      ...state,
      models: state.models.map((model) =>
        model.id === modelId ? { ...model, ...changes } : model,
      ),
      lastUpdatedAt: now(),
    };
  }
}
