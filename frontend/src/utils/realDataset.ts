import type {
  QaAgentReportDto,
  RealDatasetBBoxDto,
  RealDatasetEvaluationDto,
} from "../api/types";

export interface DisplayBoundingBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

export function boxIntersectsImage(
  bbox: DisplayBoundingBox,
  imageWidth: number,
  imageHeight: number,
): boolean {
  return (
    bbox.width > 0 &&
    bbox.height > 0 &&
    bbox.x < imageWidth &&
    bbox.y < imageHeight &&
    bbox.x + bbox.width > 0 &&
    bbox.y + bbox.height > 0
  );
}

export function apiBoxIntersectsImage(
  bbox: RealDatasetBBoxDto,
  imageWidth: number,
  imageHeight: number,
): boolean {
  return boxIntersectsImage(
    {
      x: bbox.x1,
      y: bbox.y1,
      width: bbox.x2 - bbox.x1,
      height: bbox.y2 - bbox.y1,
    },
    imageWidth,
    imageHeight,
  );
}

export function reportForSelectedImage(
  evaluation: RealDatasetEvaluationDto | undefined,
  selectedImageId: string | undefined,
): QaAgentReportDto | undefined {
  if (!evaluation || evaluation.image.id !== selectedImageId) {
    return undefined;
  }
  return evaluation.report;
}
