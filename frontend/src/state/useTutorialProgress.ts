import { useCallback, useEffect, useMemo, useState } from "react";
import { TUTORIAL_VERSION, tutorialByRole } from "../config/tutorialContent";
import type { User } from "../domain/types";

interface StoredTutorialProgress {
  version: number;
  welcomeSeen: boolean;
  completedStepIds: string[];
  completedAt?: string;
}

const storagePrefix = "label-guardian:tutorial";

function storageKey(user: User): string {
  return `${storagePrefix}:v${TUTORIAL_VERSION}:${user.id}:${user.role}`;
}

function emptyProgress(): StoredTutorialProgress {
  return {
    version: TUTORIAL_VERSION,
    welcomeSeen: false,
    completedStepIds: [],
  };
}

function readProgress(user: User | null): StoredTutorialProgress {
  if (!user) return emptyProgress();
  try {
    const raw = localStorage.getItem(storageKey(user));
    if (!raw) return emptyProgress();
    const parsed = JSON.parse(raw) as Partial<StoredTutorialProgress>;
    if (parsed.version !== TUTORIAL_VERSION) return emptyProgress();
    return {
      version: TUTORIAL_VERSION,
      welcomeSeen: parsed.welcomeSeen === true,
      completedStepIds: Array.isArray(parsed.completedStepIds)
        ? parsed.completedStepIds.filter(
            (stepId): stepId is string => typeof stepId === "string",
          )
        : [],
      completedAt:
        typeof parsed.completedAt === "string" ? parsed.completedAt : undefined,
    };
  } catch {
    return emptyProgress();
  }
}

export function useTutorialProgress(user: User | null) {
  const currentStorageKey = user ? storageKey(user) : "";
  const [progress, setProgress] = useState<StoredTutorialProgress>(() =>
    readProgress(user),
  );
  const [progressOwnerKey, setProgressOwnerKey] = useState(currentStorageKey);

  useEffect(() => {
    setProgress(readProgress(user));
    setProgressOwnerKey(currentStorageKey);
  }, [currentStorageKey, user]);

  const updateProgress = useCallback(
    (updater: (current: StoredTutorialProgress) => StoredTutorialProgress) => {
      if (!user) return;
      setProgress((current) => {
        const next = updater(current);
        localStorage.setItem(storageKey(user), JSON.stringify(next));
        return next;
      });
    },
    [user],
  );

  const markWelcomeSeen = useCallback(() => {
    updateProgress((current) => ({ ...current, welcomeSeen: true }));
  }, [updateProgress]);

  const toggleStep = useCallback(
    (stepId: string) => {
      updateProgress((current) => {
        const completed = new Set(current.completedStepIds);
        completed.has(stepId) ? completed.delete(stepId) : completed.add(stepId);
        return {
          ...current,
          completedStepIds: [...completed],
          completedAt: undefined,
        };
      });
    },
    [updateProgress],
  );

  const completeTutorial = useCallback(() => {
    if (!user) return;
    const allStepIds = tutorialByRole[user.role].steps.map((step) => step.id);
    updateProgress((current) => ({
      ...current,
      welcomeSeen: true,
      completedStepIds: allStepIds,
      completedAt: new Date().toISOString(),
    }));
  }, [updateProgress, user]);

  const resetTutorial = useCallback(() => {
    if (!user) return;
    const reset = { ...emptyProgress(), welcomeSeen: true };
    localStorage.setItem(storageKey(user), JSON.stringify(reset));
    setProgress(reset);
  }, [user]);

  const validStepIds = useMemo(
    () => new Set(user ? tutorialByRole[user.role].steps.map((step) => step.id) : []),
    [user],
  );
  const completedStepIds = useMemo(
    () => progress.completedStepIds.filter((stepId) => validStepIds.has(stepId)),
    [progress.completedStepIds, validStepIds],
  );
  const progressReady = progressOwnerKey === currentStorageKey;

  return {
    version: TUTORIAL_VERSION,
    showWelcome: Boolean(user) && progressReady && !progress.welcomeSeen,
    completedStepIds: progressReady ? completedStepIds : [],
    completedAt: progressReady ? progress.completedAt : undefined,
    markWelcomeSeen,
    toggleStep,
    completeTutorial,
    resetTutorial,
  };
}
