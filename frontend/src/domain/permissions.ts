import type { Finding, Role } from "./types.ts";

export function canEditAnnotation(
  finding: Finding,
  role: Role,
  activeUserId: string,
): boolean {
  return role === "reviewer" || (role === "annotator" && finding.assigneeId === activeUserId);
}

export function canSubmitAnnotatorFeedback(
  finding: Finding,
  role: Role,
  activeUserId: string,
): boolean {
  return role === "annotator" && finding.assigneeId === activeUserId;
}
