import type { CandidateReport } from "@/lib/types";

export interface WeightedPart {
  name: string;
  weight: number;
  /** Average score out of 10 of the scored features in this group, or null when none were scored. */
  average: number | null;
  features: number;
}

/**
 * The role's weighted score for one report, from the role's weights as they are now. A criterion counts the scored
 * features whose group has the same name; criteria with no scored features are shown but left out of the total, so
 * "could not test" never pulls a candidate down. Nothing is re-tested: changing a weight changes this at once.
 */
export function weightedScore(
  report: CandidateReport,
  criteria: { name: string; weight: number }[],
): { score: number | null; parts: WeightedPart[] } {
  const features = report.projects.flatMap((p) => p.features).filter((f) => f.score10 !== null);
  const parts = criteria.map((c) => {
    const inGroup = features.filter((f) => (f.group ?? "").toLowerCase() === c.name.toLowerCase());
    const average = inGroup.length ? inGroup.reduce((sum, f) => sum + (f.score10 ?? 0), 0) / inGroup.length : null;
    return { name: c.name, weight: c.weight, average, features: inGroup.length };
  });
  const used = parts.filter((p) => p.average !== null);
  const weights = used.reduce((sum, p) => sum + p.weight, 0);
  const score = weights ? used.reduce((sum, p) => sum + p.weight * (p.average as number), 0) / weights : null;
  return { score: score === null ? null : Math.round(score * 10) / 10, parts };
}
