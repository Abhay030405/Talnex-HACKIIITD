import type { JobRow } from "@/lib/types";

export interface FlowStage {
  name: string;
  status: "done" | "running" | "retrying" | "failed" | "queued" | "skipped" | "waiting";
  depth: number;
  row: number;
  job?: JobRow;
  summary: string;
}

/** A one-line summary of a job's result, never raw JSON. */
export function jobSummary(job: JobRow): string {
  const r = job.result;
  if (!r) return "";
  if (r.reused_from_run) return `reused from run ${r.reused_from_run}`;
  if (r.skipped) return `skipped${r.reason ? `: ${r.reason}` : ""}`;
  return Object.entries(r)
    .filter(([, v]) => ["string", "number", "boolean"].includes(typeof v))
    .slice(0, 3)
    .map(([k, v]) => `${k.replace(/_/g, " ")}: ${v}`)
    .join(" · ");
}

/**
 * The stages of one pipeline run laid out left to right: each stage sits one column after the deepest stage it waits
 * for. Stages seen in other runs but not yet created in this one are shown as not started.
 */
export function layoutPipeline(rows: JobRow[], allRows: JobRow[]): { stages: FlowStage[]; edges: [string, string][] } {
  const after = new Map<string, string[]>();
  for (const r of allRows) if (!after.has(r.stage)) after.set(r.stage, r.after_stages ?? []);
  const byStage = new Map(rows.map((r) => [r.stage, r]));
  const names = [...after.keys()];
  const depth = new Map<string, number>();
  const depthOf = (name: string, seen = new Set<string>()): number => {
    if (depth.has(name)) return depth.get(name)!;
    if (seen.has(name)) return 0; // a cycle cannot happen in pipeline_stages; guard anyway
    seen.add(name);
    const parents = (after.get(name) ?? []).filter((p) => after.has(p));
    const d = parents.length ? Math.max(...parents.map((p) => depthOf(p, seen))) + 1 : 0;
    depth.set(name, d);
    return d;
  };
  names.forEach((n) => depthOf(n));
  const rowsAt = new Map<number, number>();
  const stages = names
    .sort((a, b) => depth.get(a)! - depth.get(b)! || a.localeCompare(b))
    .map((name) => {
      const d = depth.get(name)!;
      const row = rowsAt.get(d) ?? 0;
      rowsAt.set(d, row + 1);
      const job = byStage.get(name);
      const status: FlowStage["status"] = !job ? "waiting" : job.status === "done" && job.result?.skipped ? "skipped" : job.status;
      return { name, status, depth: d, row, job, summary: job ? jobSummary(job) : "" };
    });
  const edges: [string, string][] = [];
  for (const name of names) for (const p of after.get(name) ?? []) if (after.has(p)) edges.push([p, name]);
  return { stages, edges };
}
