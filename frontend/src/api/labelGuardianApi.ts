import type {
  AuthenticatedUserDto,
  ApplicationUserListDto,
  AnnotationDocumentDto,
  AnnotationRevisionListDto,
  PipelineRunDto,
  PipelineRunListDto,
  QaCaseDto,
  QaCaseListDto,
  RealDatasetEvaluationDto,
  RealDatasetFrameSampleListDto,
  RealDatasetImageListDto,
} from "./types";
import { getAccessToken } from "../auth/supabase.ts";

type RuntimeImportMeta = ImportMeta & {
  env?: Record<string, string | undefined>;
};

const runtimeEnvironment = (import.meta as RuntimeImportMeta).env;
const configuredBaseUrl = runtimeEnvironment?.VITE_API_BASE_URL?.trim() ?? "";
const API_BASE_URL = configuredBaseUrl.replace(/\/$/, "");
const API_V1_PREFIX = "/api/v1";

export class LabelGuardianApiError extends Error {
  readonly status: number;
  readonly code?: string;

  constructor(
    message: string,
    status: number,
    code?: string,
  ) {
    super(message);
    this.name = "LabelGuardianApiError";
    this.status = status;
    this.code = code;
  }
}

async function requestJson<T>(
  path: string,
  signal?: AbortSignal,
  method: "GET" | "POST" | "PUT" | "PATCH" = "GET",
  body?: unknown,
  accessToken?: string,
): Promise<T> {
  const token = accessToken ?? (await getAccessToken());
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers: {
      Accept: "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(body === undefined ? {} : { "Content-Type": "application/json" }),
    },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    signal,
  });
  if (!response.ok) {
    let message = `API request failed with status ${response.status}`;
    let code: string | undefined;
    try {
      const body = (await response.json()) as { message?: string; detail?: string; code?: string };
      message = body.message ?? body.detail ?? message;
      code = body.code;
    } catch {
      // Keep the generic status message when the upstream body is not JSON.
    }
    throw new LabelGuardianApiError(message, response.status, code);
  }
  return (await response.json()) as T;
}

async function requestAsset(path: string, signal?: AbortSignal): Promise<Blob> {
  const resolvedUrl = path.startsWith("http://") || path.startsWith("https://")
    ? path
    : `${API_BASE_URL}${path}`;
  const token = await getAccessToken();
  const target = new URL(resolvedUrl, window.location.origin);
  const apiOrigin = new URL(API_BASE_URL || window.location.origin, window.location.origin).origin;
  const response = await fetch(target, {
    headers: token && target.origin === apiOrigin
      ? { Authorization: `Bearer ${token}` }
      : undefined,
    signal,
  });
  if (!response.ok) {
    throw new LabelGuardianApiError(
      `Không thể tải ảnh (HTTP ${response.status}).`,
      response.status,
    );
  }
  return response.blob();
}

export const labelGuardianApiV1 = {
  getMyProfile(accessToken: string, signal?: AbortSignal): Promise<AuthenticatedUserDto> {
    return requestJson<AuthenticatedUserDto>(
      `${API_V1_PREFIX}/auth/me`,
      signal,
      "GET",
      undefined,
      accessToken,
    );
  },

  fetchAsset(path: string, signal?: AbortSignal): Promise<Blob> {
    return requestAsset(path, signal);
  },

  listApplicationUsers(signal?: AbortSignal): Promise<ApplicationUserListDto> {
    return requestJson<ApplicationUserListDto>(`${API_V1_PREFIX}/auth/users`, signal);
  },

  updateApplicationUserRole(
    userId: string,
    role: AuthenticatedUserDto["role"],
    signal?: AbortSignal,
  ): Promise<AuthenticatedUserDto> {
    return requestJson<AuthenticatedUserDto>(
      `${API_V1_PREFIX}/auth/users/${encodeURIComponent(userId)}/role`,
      signal,
      "PATCH",
      { role },
    );
  },

  listQaCases(
    signal?: AbortSignal,
    filters: { split?: string; sourceImageId?: string } = {},
  ): Promise<QaCaseListDto> {
    const parameters = new URLSearchParams({ limit: "200" });
    if (filters.split) parameters.set("split", filters.split);
    if (filters.sourceImageId) parameters.set("sourceImageId", filters.sourceImageId);
    return requestJson<QaCaseListDto>(`${API_V1_PREFIX}/qa-cases?${parameters}`, signal);
  },

  updateQaCaseStatus(
    caseId: string,
    status: "in_review" | "confirmed" | "rejected" | "skipped",
    actorId?: string,
    reason?: string,
    signal?: AbortSignal,
  ): Promise<QaCaseDto> {
    return requestJson<QaCaseDto>(
      `${API_V1_PREFIX}/qa-cases/${encodeURIComponent(caseId)}/status`,
      signal,
      "POST",
      { status, actorId, reason },
    );
  },

  listRealDatasetImages(
    split: string | undefined,
    offset = 0,
    signal?: AbortSignal,
    dataset?: string,
  ): Promise<RealDatasetImageListDto> {
    const parameters = new URLSearchParams({ limit: "24", offset: String(offset) });
    if (split) parameters.set("split", split);
    if (dataset) parameters.set("dataset", dataset);
    return requestJson<RealDatasetImageListDto>(`${API_V1_PREFIX}/dataset/images?${parameters}`, signal);
  },

  listRealDatasetFrameSamples(
    split: string | undefined,
    offset = 0,
    signal?: AbortSignal,
    dataset?: string,
  ): Promise<RealDatasetFrameSampleListDto> {
    const parameters = new URLSearchParams({ limit: "8", offset: String(offset) });
    if (split) parameters.set("split", split);
    if (dataset) parameters.set("dataset", dataset);
    return requestJson<RealDatasetFrameSampleListDto>(`${API_V1_PREFIX}/dataset/frame-samples?${parameters}`, signal);
  },

  evaluateRealDatasetImage(
    split: string,
    imageId: string,
    force = false,
    persist = true,
    signal?: AbortSignal,
  ): Promise<RealDatasetEvaluationDto> {
    const parameters = new URLSearchParams({
      force: String(force),
      persist: String(persist),
    });
    return requestJson<RealDatasetEvaluationDto>(
      `${API_V1_PREFIX}/dataset/images/${encodeURIComponent(split)}/${encodeURIComponent(imageId)}/evaluate?${parameters}`,
      signal,
      "POST",
    );
  },

  getImageAnnotations(split: string, imageId: string, signal?: AbortSignal): Promise<AnnotationDocumentDto> {
    return requestJson<AnnotationDocumentDto>(
      `${API_V1_PREFIX}/dataset/images/${encodeURIComponent(split)}/${encodeURIComponent(imageId)}/annotations`,
      signal,
    );
  },

  saveImageAnnotations(
    split: string,
    imageId: string,
    payload: { expectedRevision: number; labels: RealDatasetImageListDto["results"][number]["labels"]; actorId?: string; changeNote?: string },
    signal?: AbortSignal,
  ): Promise<AnnotationDocumentDto> {
    return requestJson<AnnotationDocumentDto>(
      `${API_V1_PREFIX}/dataset/images/${encodeURIComponent(split)}/${encodeURIComponent(imageId)}/annotations`,
      signal,
      "PUT",
      payload,
    );
  },

  getImageAnnotationHistory(split: string, imageId: string, signal?: AbortSignal): Promise<AnnotationRevisionListDto> {
    return requestJson<AnnotationRevisionListDto>(
      `${API_V1_PREFIX}/dataset/images/${encodeURIComponent(split)}/${encodeURIComponent(imageId)}/annotations/history`,
      signal,
    );
  },

  restoreImageAnnotations(
    split: string,
    imageId: string,
    payload: { expectedRevision: number; targetRevision: number; actorId?: string; changeNote?: string },
    signal?: AbortSignal,
  ): Promise<AnnotationDocumentDto> {
    return requestJson<AnnotationDocumentDto>(
      `${API_V1_PREFIX}/dataset/images/${encodeURIComponent(split)}/${encodeURIComponent(imageId)}/annotations/restore`,
      signal,
      "POST",
      payload,
    );
  },

  listPipelineRuns(signal?: AbortSignal): Promise<PipelineRunListDto> {
    return requestJson<PipelineRunListDto>(`${API_V1_PREFIX}/ingestion/runs?limit=20`, signal);
  },

  getPipelineRun(runId: string, signal?: AbortSignal): Promise<PipelineRunDto> {
    return requestJson<PipelineRunDto>(`${API_V1_PREFIX}/ingestion/runs/${encodeURIComponent(runId)}`, signal);
  },

  resolveAssetUrl(path: string): string {
    return path.startsWith("http://") || path.startsWith("https://") ? path : `${API_BASE_URL}${path}`;
  },
};

/** @deprecated Use labelGuardianApiV1 in new code. */
export const labelGuardianApi = labelGuardianApiV1;

export function isApiDataSourceEnabled(): boolean {
  return (runtimeEnvironment?.VITE_DATA_SOURCE ?? "api").toLowerCase() === "api";
}
