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
  const engineering = report.projects.map((p) => p.engineering?.overall).filter((s): s is number => typeof s === "number");
  const parts = criteria.map((c) => {
    // A criterion called "Engineering" weighs the repository engineering quality instead of a feature group.
    if (c.name.trim().toLowerCase() === "engineering") {
      const average = engineering.length ? engineering.reduce((a, b) => a + b, 0) / engineering.length : null;
      return { name: c.name, weight: c.weight, average, features: engineering.length };
    }
    const inGroup = features.filter((f) => (f.group ?? "").toLowerCase() === c.name.toLowerCase());
    const average = inGroup.length ? inGroup.reduce((sum, f) => sum + (f.score10 ?? 0), 0) / inGroup.length : null;
    return { name: c.name, weight: c.weight, average, features: inGroup.length };
  });
  const used = parts.filter((p) => p.average !== null);
  const weights = used.reduce((sum, p) => sum + p.weight, 0);
  const score = weights ? used.reduce((sum, p) => sum + p.weight * (p.average as number), 0) / weights : null;
  return { score: score === null ? null : Math.round(score * 10) / 10, parts };
}

/**
 * A hackathon card's weighted total from its criterion group scores (0 to 100) and the event's weights as they are now.
 * Same rule as the worker: unscored criteria are left out and the rest rescaled; weight_covered says how much counts.
 */
export function weightedFromGroups(
  groups: { group: string; score: number | null }[],
  criteria: { name: string; weight: number }[],
): { score: number | null; weight_covered: number; criteria_used: number; criteria_total: number } {
  const scoreOf = (name: string) => groups.find((g) => g.group.toLowerCase() === name.toLowerCase())?.score ?? null;
  const total = criteria.reduce((sum, c) => sum + c.weight, 0);
  const scored = criteria.filter((c) => scoreOf(c.name) !== null);
  const used = scored.reduce((sum, c) => sum + c.weight, 0);
  if (!scored.length || total <= 0) return { score: null, weight_covered: 0, criteria_used: 0, criteria_total: criteria.length };
  return {
    score: Math.round((scored.reduce((sum, c) => sum + c.weight * (scoreOf(c.name) as number), 0) / used) * 10) / 10,
    weight_covered: Math.round((1000 * used) / total) / 10,
    criteria_used: scored.length,
    criteria_total: criteria.length,
  };
}
