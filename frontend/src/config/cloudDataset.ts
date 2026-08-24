import type { Dataset, DatasetFormat } from "../domain/types";

const environment = import.meta.env;

function datasetFormat(value: string | undefined): DatasetFormat {
  return value?.trim().toLowerCase() === "kitti" ? "KITTI" : "nuScenes";
}

const datasetId = environment.VITE_DATASET_ID?.trim() || "nuscenes";
const datasetVersion = environment.VITE_DATASET_VERSION?.trim() || "v1.0-mini";
const format = datasetFormat(environment.VITE_DATASET_FORMAT);

/**
 * The current API process is intentionally scoped to one DATASET_ID/release.
 * Keeping the browser selector aligned prevents links that ask the backend for
 * a dataset the deployed service cannot serve.
 */
export const cloudDatasets: Dataset[] = [
  {
    id: datasetId,
    name: environment.VITE_DATASET_NAME?.trim() || `${format} cloud dataset`,
    format,
    version: datasetVersion,
    description: `Private ${format} frames and annotations served through the API.`,
    sceneCount: 0,
    frameCount: 0,
    annotationCount: 0,
    anonymized: true,
  },
];
