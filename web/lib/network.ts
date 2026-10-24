// What the browser's developer tools saw during a project's live tests (ai/talnex_ai/testing/runner/devtools.py),
// summed up for the project card. Evidence beside the verdicts, never a verdict on its own.
import type { DevtoolsRecord, ReportFeature } from "@/lib/types";

export const SLOW_MS = 2000;

export interface NetworkSummary {
  apiCalls: number;
  averageMs: number | null;
  slowestMs: number | null;
  errors: number;
  consoleErrors: number;
  leaks: number;
}

/** Totals over every step of every feature; null when no step recorded anything. */
export function networkSummary(features: Pick<ReportFeature, "proof">[]): NetworkSummary | null {
  const records = features.flatMap((f) => f.proof).map((s) => s.devtools).filter((d): d is DevtoolsRecord => !!d);
  if (records.length === 0) return null;
  const times = records.flatMap((d) => d.api_calls ?? []).map((c) => c.ms).filter((ms): ms is number => typeof ms === "number");
  return {
    apiCalls: records.reduce((n, d) => n + (d.api_calls?.length ?? 0), 0),
    averageMs: times.length ? Math.round(times.reduce((a, b) => a + b, 0) / times.length) : null,
    slowestMs: times.length ? Math.max(...times) : null,
    errors: records.reduce((n, d) => n + (d.error_responses?.length ?? 0) + (d.failed_requests?.length ?? 0), 0),
    consoleErrors: records.reduce((n, d) => n + (d.console_errors?.length ?? 0) + (d.page_errors?.length ?? 0), 0),
    leaks: records.reduce((n, d) => n + (d.leaks?.length ?? 0), 0),
  };
}
