import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { labelGuardianApiV1 } from "./labelGuardianApi";
import type { RealDatasetLabelDto } from "./types";

export const apiQueryKeys = {
  qaCases: ["api-v1", "qa-cases"] as const,
  qaCasesForImage: (split?: string, imageId?: string) =>
    ["api-v1", "qa-cases", split, imageId] as const,
  realDatasetImages: (split: string | undefined, dataset: string | undefined, offset: number) =>
    ["api-v1", "dataset", "images", split, dataset, offset] as const,
  realDatasetFrameSamples: (split: string | undefined, dataset: string | undefined, offset: number) =>
    ["api-v1", "dataset", "frame-samples", split, dataset, offset] as const,
  annotations: (split?: string, imageId?: string) =>
    ["api-v1", "dataset", "annotations", split, imageId] as const,
  annotationHistory: (split?: string, imageId?: string) =>
    ["api-v1", "dataset", "annotations", split, imageId, "history"] as const,
  applicationUsers: ["api-v1", "auth", "users"] as const,
};

export function useApplicationUsersQuery(enabled = true) {
  return useQuery({
    queryKey: apiQueryKeys.applicationUsers,
    queryFn: ({ signal }) => labelGuardianApiV1.listApplicationUsers(signal),
    enabled,
  });
}

export function useUpdateApplicationUserRoleMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ userId, role }: { userId: string; role: "annotator" | "reviewer" | "admin" }) =>
      labelGuardianApiV1.updateApplicationUserRole(userId, role),
    onSuccess: async () => queryClient.invalidateQueries({ queryKey: apiQueryKeys.applicationUsers }),
  });
}

export function useQaCasesQuery(
  filters: { split?: string; sourceImageId?: string } = {},
  enabled = true,
) {
  return useQuery({
    queryKey: filters.sourceImageId
      ? apiQueryKeys.qaCasesForImage(filters.split, filters.sourceImageId)
      : apiQueryKeys.qaCases,
    queryFn: ({ signal }) => labelGuardianApiV1.listQaCases(signal, filters),
    enabled,
  });
}

export function useRealDatasetImagesQuery(split: string | undefined, offset: number, dataset?: string) {
  return useQuery({
    queryKey: apiQueryKeys.realDatasetImages(split, dataset, offset),
    queryFn: ({ signal }) => labelGuardianApiV1.listRealDatasetImages(split, offset, signal, dataset),
  });
}

export function useRealDatasetFrameSamplesQuery(split: string | undefined, offset: number, dataset?: string) {
  return useQuery({
    queryKey: apiQueryKeys.realDatasetFrameSamples(split, dataset, offset),
    queryFn: ({ signal }) => labelGuardianApiV1.listRealDatasetFrameSamples(split, offset, signal, dataset),
  });
}

export function useEvaluateRealDatasetImageMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      split,
      imageId,
      force = false,
      persist = true,
    }: {
      split: string;
      imageId: string;
      force?: boolean;
      persist?: boolean;
    }) =>
      labelGuardianApiV1.evaluateRealDatasetImage(
        split,
        imageId,
        force,
        persist,
      ),
    onSuccess: async () =>
      queryClient.invalidateQueries({ queryKey: apiQueryKeys.qaCases }),
  });
}

export function useQaCaseStatusMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      caseId,
      status,
      actorId,
      reason,
    }: {
      caseId: string;
      status: "in_review" | "confirmed" | "rejected" | "skipped";
      actorId?: string;
      reason?: string;
    }) =>
      labelGuardianApiV1.updateQaCaseStatus(caseId, status, actorId, reason),
    onSuccess: async () =>
      queryClient.invalidateQueries({ queryKey: apiQueryKeys.qaCases }),
  });
}

export function useImageAnnotationsQuery(split?: string, imageId?: string) {
  return useQuery({
    queryKey: apiQueryKeys.annotations(split, imageId),
    queryFn: ({ signal }) =>
      labelGuardianApiV1.getImageAnnotations(split!, imageId!, signal),
    enabled: Boolean(split && imageId),
  });
}

export function useAnnotationHistoryQuery(split?: string, imageId?: string) {
  return useQuery({
    queryKey: apiQueryKeys.annotationHistory(split, imageId),
    queryFn: ({ signal }) =>
      labelGuardianApiV1.getImageAnnotationHistory(split!, imageId!, signal),
    enabled: Boolean(split && imageId),
  });
}

export function useSaveAnnotationsMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      split,
      imageId,
      expectedRevision,
      labels,
      actorId,
      changeNote,
    }: {
      split: string;
      imageId: string;
      expectedRevision: number;
      labels: RealDatasetLabelDto[];
      actorId?: string;
      changeNote?: string;
    }) =>
      labelGuardianApiV1.saveImageAnnotations(split, imageId, {
        expectedRevision,
        labels,
        actorId,
        changeNote,
      }),
    onSuccess: async (_data, variables) => {
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: apiQueryKeys.annotations(
            variables.split,
            variables.imageId,
          ),
        }),
        queryClient.invalidateQueries({
          queryKey: apiQueryKeys.annotationHistory(
            variables.split,
            variables.imageId,
          ),
        }),
        queryClient.invalidateQueries({ queryKey: ["api-v1", "dataset"] }),
        queryClient.invalidateQueries({ queryKey: apiQueryKeys.qaCases }),
      ]);
    },
  });
}

export function useRestoreAnnotationsMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      split,
      imageId,
      expectedRevision,
      targetRevision,
      actorId,
    }: {
      split: string;
      imageId: string;
      expectedRevision: number;
      targetRevision: number;
      actorId?: string;
    }) =>
      labelGuardianApiV1.restoreImageAnnotations(split, imageId, {
        expectedRevision,
        targetRevision,
        actorId,
      }),
    onSuccess: async (_data, variables) => {
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: apiQueryKeys.annotations(
            variables.split,
            variables.imageId,
          ),
        }),
        queryClient.invalidateQueries({
          queryKey: apiQueryKeys.annotationHistory(
            variables.split,
            variables.imageId,
          ),
        }),
        queryClient.invalidateQueries({ queryKey: ["api-v1", "dataset"] }),
        queryClient.invalidateQueries({ queryKey: apiQueryKeys.qaCases }),
      ]);
    },
  });
}
