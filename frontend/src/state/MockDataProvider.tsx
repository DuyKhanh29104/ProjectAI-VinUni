import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useReducer,
  type PropsWithChildren,
} from "react";
import { createInitialMockState } from "../data/mockData";
import { MockRepository } from "./mockRepository";
import type { LabelGuardianRepository } from "./repository";
import type { MockState, ReviewStatus, Role } from "../domain/types";

const STORAGE_KEY = "label-guardian:mock-state:v2";
const repository: LabelGuardianRepository = new MockRepository();

type Action =
  | { type: "set_role"; role: Role }
  | { type: "set_dataset"; datasetId: string }
  | { type: "start_qa_run"; datasetId: string }
  | { type: "advance_qa_run" }
  | {
      type: "update_rule";
      ruleId: string;
      changes: { enabled?: boolean; threshold?: number };
    }
  | {
      type: "update_model";
      modelId: string;
      changes: { enabled?: boolean; confidenceThreshold?: number };
    }
  | {
      type: "set_finding_status";
      findingId: string;
      status: ReviewStatus;
      userId: string;
      action: "start_review" | "confirm" | "reject_finding" | "skip";
      reason?: string;
    }
  | {
      type: "approve_finding";
      findingId: string;
      userId: string;
      reason?: string;
    }
  | {
      type: "add_feedback";
      findingId: string;
      userId: string;
      feedback: string;
    }
  | {
      type: "assign_finding";
      findingId: string;
      assigneeId: string;
      userId: string;
    }
  | { type: "reset" };

function loadInitialState(): MockState {
  const seed = createInitialMockState();
  if (typeof window === "undefined") {
    return seed;
  }

  const persisted = window.localStorage.getItem(STORAGE_KEY);
  if (!persisted) {
    return seed;
  }

  try {
    const parsed = JSON.parse(persisted) as Partial<MockState>;
    return {
      ...seed,
      ...parsed,
      qaRun: parsed.qaRun ?? seed.qaRun,
      rules: parsed.rules ?? seed.rules,
      models: parsed.models ?? seed.models,
    };
  } catch {
    return seed;
  }
}

function reducer(state: MockState, action: Action): MockState {
  switch (action.type) {
    case "set_role":
      return repository.setActiveRole(state, action.role);
    case "set_dataset":
      return repository.setSelectedDataset(state, action.datasetId);
    case "start_qa_run":
      return repository.startQaRun(state, action.datasetId);
    case "advance_qa_run":
      return repository.advanceQaRun(state);
    case "update_rule":
      return repository.updateRule(state, action.ruleId, action.changes);
    case "update_model":
      return repository.updateModel(state, action.modelId, action.changes);
    case "set_finding_status":
      return repository.setFindingStatus(
        state,
        action.findingId,
        action.status,
        action.userId,
        action.action,
        action.reason,
      );
    case "approve_finding":
      return repository.approveFinding(
        state,
        action.findingId,
        action.userId,
        action.reason,
      );
    case "add_feedback":
      return repository.addFindingFeedback(
        state,
        action.findingId,
        action.userId,
        action.feedback,
      );
    case "assign_finding":
      return repository.assignFinding(
        state,
        action.findingId,
        action.assigneeId,
        action.userId,
      );
    case "reset":
      return repository.reset();
    default:
      return state;
  }
}

interface MockDataContextValue {
  state: MockState;
  actions: {
    setRole: (role: Role) => void;
    setDataset: (datasetId: string) => void;
    startQaRun: (datasetId: string) => void;
    advanceQaRun: () => void;
    updateRule: (ruleId: string, changes: { enabled?: boolean; threshold?: number }) => void;
    updateModel: (modelId: string, changes: { enabled?: boolean; confidenceThreshold?: number }) => void;
    setFindingStatus: (
      findingId: string,
      status: ReviewStatus,
      action: "start_review" | "confirm" | "reject_finding" | "skip",
      reason?: string,
    ) => void;
    approveFinding: (findingId: string, reason?: string) => void;
    submitFeedback: (findingId: string, feedback: string) => void;
    assignFinding: (findingId: string, assigneeId: string) => void;
    reset: () => void;
  };
}

const MockDataContext = createContext<MockDataContextValue | undefined>(
  undefined,
);

export function MockDataProvider({ children }: PropsWithChildren) {
  const [state, dispatch] = useReducer(reducer, undefined, loadInitialState);

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  }, [state]);

  const actions = useMemo<MockDataContextValue["actions"]>(
    () => ({
      setRole: (role) => dispatch({ type: "set_role", role }),
      setDataset: (datasetId) => dispatch({ type: "set_dataset", datasetId }),
      startQaRun: (datasetId) => dispatch({ type: "start_qa_run", datasetId }),
      advanceQaRun: () => dispatch({ type: "advance_qa_run" }),
      updateRule: (ruleId, changes) => dispatch({ type: "update_rule", ruleId, changes }),
      updateModel: (modelId, changes) => dispatch({ type: "update_model", modelId, changes }),
      setFindingStatus: (findingId, status, action, reason) =>
        dispatch({
          type: "set_finding_status",
          findingId,
          status,
          action,
          userId: state.activeUserId,
          reason,
        }),
      approveFinding: (findingId, reason) =>
        dispatch({
          type: "approve_finding",
          findingId,
          userId: state.activeUserId,
          reason,
        }),
      submitFeedback: (findingId, feedback) =>
        dispatch({
          type: "add_feedback",
          findingId,
          userId: state.activeUserId,
          feedback,
        }),
      assignFinding: (findingId, assigneeId) =>
        dispatch({
          type: "assign_finding",
          findingId,
          assigneeId,
          userId: state.activeUserId,
        }),
      reset: () => dispatch({ type: "reset" }),
    }),
    [state.activeUserId],
  );

  const value = useMemo(() => ({ state, actions }), [actions, state]);

  return (
    <MockDataContext.Provider value={value}>
      {children}
    </MockDataContext.Provider>
  );
}

export function useMockData(): MockDataContextValue {
  const context = useContext(MockDataContext);
  if (!context) {
    throw new Error("useMockData must be used inside MockDataProvider");
  }
  return context;
}
