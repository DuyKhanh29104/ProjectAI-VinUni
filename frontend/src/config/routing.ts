import { appRoutes } from "./informationArchitecture.ts";
import type { PrimaryViewId } from "../components/layout.tsx";

export function viewFromPath(pathname: string): PrimaryViewId {
  if (pathname.startsWith("/cases/")) return "case-detail";
  const route = appRoutes.find((item) => item.path === pathname);
  return (route?.id as PrimaryViewId | undefined) ?? "overview";
}

export function pathForView(view: PrimaryViewId): string {
  return appRoutes.find((item) => item.id === view)?.path ?? "/overview";
}

/**
 * Build a top-level navigation URL without leaking frame-scoped parameters
 * such as split/imageId from the Editor or a QA Cases deeplink.
 */
export function pathForDatasetView(
  view: PrimaryViewId,
  datasetId?: string,
): string {
  const path = pathForView(view);
  const normalizedDatasetId = datasetId?.trim();
  if (!normalizedDatasetId) return path;

  const parameters = new URLSearchParams({ dataset: normalizedDatasetId });
  return `${path}?${parameters.toString()}`;
}
