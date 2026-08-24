import type { Finding, FindingType, ReviewStatus, Severity } from "./types";

export type QueueSortKey = "priority" | "risk" | "newest";

export interface QueueFilterOptions {
  query: string;
  status: ReviewStatus | "all";
  severity: Severity | "all";
  type: FindingType | "all";
  sceneId: string;
  risk: "all" | "high" | "critical";
  sortBy: QueueSortKey;
  sceneIds: Set<string>;
  searchTextByFindingId?: Map<string, string>;
}

export function filterAndSortFindings(
  findings: Finding[],
  options: QueueFilterOptions,
): Finding[] {
  const query = options.query.trim().toLowerCase();
  const visible = findings.filter((finding) => {
    if (!options.sceneIds.has(finding.sceneId)) {
      return false;
    }

    const searchable = options.searchTextByFindingId?.get(finding.id) ?? [
      finding.id,
      finding.title,
      finding.summary,
      finding.type,
      finding.trackId,
    ].filter(Boolean).join(" ");
    const matchesQuery = !query || searchable.toLowerCase().includes(query);
    const matchesStatus = options.status === "all" || finding.status === options.status;
    const matchesSeverity = options.severity === "all" || finding.severity === options.severity;
    const matchesType = options.type === "all" || finding.type === options.type;
    const matchesScene = options.sceneId === "all" || finding.sceneId === options.sceneId;
    const matchesRisk = options.risk === "all"
      || (options.risk === "high" && finding.riskScore >= 0.8)
      || (options.risk === "critical" && finding.riskScore >= 0.9);

    return matchesQuery && matchesStatus && matchesSeverity && matchesType && matchesScene && matchesRisk;
  });

  return [...visible].sort((first, second) => {
    if (options.sortBy === "risk") {
      return second.riskScore - first.riskScore;
    }
    if (options.sortBy === "newest") {
      return second.createdAt.localeCompare(first.createdAt);
    }
    return first.priority - second.priority;
  });
}
