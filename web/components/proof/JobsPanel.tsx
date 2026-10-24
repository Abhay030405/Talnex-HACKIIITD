"use client";

import { useState, useTransition } from "react";

import { retryJobAction, runStagesAction } from "@/app/jobs-actions";
import { AutoRefresh } from "@/components/ui/AutoRefresh";
import type { JobRow } from "@/lib/types";

const STATUS_BADGE: Record<JobRow["status"], string> = {
  done: "badge badge--success",
  running: "badge badge--warning",
  queued: "badge badge--neutral",
  retrying: "badge badge--warning",
  failed: "badge badge--danger",
};

/** Where "run these stages again" goes, for the pipelines that can be re-run stage by stage. */
function runPath(job: JobRow): string | null {
  const id = encodeURIComponent(job.target_id);
  if (job.pipeline === "recruiter" && job.target_type === "candidate_project") return `/v1/candidate-projects/${id}/run-stages`;
  if (job.pipeline === "recruiter_coding" && job.target_type === "candidate") return `/v1/candidates/${id}/run-stages`;
  if (job.pipeline === "hackathon" && job.target_type === "project") return `/v1/projects/${id}/run-stages`;
  return null;
}

function summary(job: JobRow): string {
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
 * Every job of a check, grouped by project and pipeline: pick a run, then run one stage again, several chosen stages,
 * or retry a failed job. Earlier stages are reused, the stages after the chosen ones run again, and the live view opens.
 */
export function JobsPanel({ jobs, liveHref }: { jobs: JobRow[]; liveHref: string }) {
  const [pending, start] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const [picked, setPicked] = useState<Record<string, string[]>>({});
  const groups = new Map<string, JobRow[]>();
  for (const job of jobs) {
    const key = `${job.pipeline}|${job.target_id}`;
    groups.set(key, [...(groups.get(key) ?? []), job]);
  }
  const busy = jobs.some((j) => j.status === "queued" || j.status === "running" || j.status === "retrying");
  if (jobs.length === 0) return null;

  const go = (action: () => Promise<{ error?: string }>) =>
    start(async () => {
      const result = await action();
      if (result?.error) setError(result.error);
    });

  return (
    <details className="proof-viewer">
      <summary>Jobs ({jobs.length})</summary>
      <AutoRefresh active={busy} />
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      {[...groups.entries()].map(([key, rows]) => (
        <JobGroup
          key={key}
          rows={rows}
          picked={picked[key] ?? []}
          onPick={(stages) => setPicked({ ...picked, [key]: stages })}
          pending={pending}
          run={(path, stages) => go(() => runStagesAction(path, stages, liveHref))}
          retry={(id) => go(() => retryJobAction(id, liveHref))}
        />
      ))}
    </details>
  );
}

function JobGroup({
  rows,
  picked,
  onPick,
  pending,
  run,
  retry,
}: {
  rows: JobRow[];
  picked: string[];
  onPick: (stages: string[]) => void;
  pending: boolean;
  run: (path: string, stages: string[]) => void;
  retry: (id: string) => void;
}) {
  const runs = [...new Set(rows.map((r) => r.run))].sort((a, b) => b - a);
  const [shown, setShown] = useState(runs[0]);
  const inRun = rows.filter((r) => r.run === shown);
  const first = rows[0];
  const path = runPath(first);
  const title = `${first.project ? `${first.project} · ` : ""}${first.pipeline.replace(/_/g, " ")}`;
  const toggle = (stage: string) => onPick(picked.includes(stage) ? picked.filter((s) => s !== stage) : [...picked, stage]);

  return (
    <div className="jobs-panel__group">
      <div className="row">
        <strong>{title}</strong>
        <label className="meta">
          Run{" "}
          <select className="input jobs-panel__run" value={shown} onChange={(e) => setShown(Number(e.target.value))} aria-label={`Run of ${title}`}>
            {runs.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>
        {path && (
          <button
            type="button"
            className="button button--sm"
            disabled={pending || picked.length === 0}
            onClick={() => run(path, picked)}
          >
            Run selected{picked.length ? ` (${picked.length})` : ""}
          </button>
        )}
      </div>
      <div className="table__wrap">
        <table className="table">
          <thead>
            <tr>
              {path && (
                <th scope="col">
                  <span className="sr-only">Choose</span>
                </th>
              )}
              <th scope="col">Stage</th>
              <th scope="col">Status</th>
              <th scope="col">Tries</th>
              <th scope="col">Time</th>
              <th scope="col">Result or error</th>
              <th scope="col">
                <span className="sr-only">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {inRun.map((job) => (
              <tr key={job.id} className="table__row--static">
                {path && (
                  <td>
                    <input
                      type="checkbox"
                      checked={picked.includes(job.stage)}
                      onChange={() => toggle(job.stage)}
                      aria-label={`Choose ${job.stage}`}
                    />
                  </td>
                )}
                <td>{job.stage.replace(/_/g, " ")}</td>
                <td>
                  <span className={STATUS_BADGE[job.status]}>{job.status}</span>
                </td>
                <td>
                  {job.tries}/{job.max_tries}
                </td>
                <td>{job.status === "done" || job.status === "failed" ? `${Math.round(job.seconds)}s` : "…"}</td>
                <td className="table__wrap-text">{job.error || summary(job)}</td>
                <td className="table__end">
                  {job.status === "failed" && (
                    <button type="button" className="button button--ghost button--sm" disabled={pending} onClick={() => retry(job.id)}>
                      Retry
                    </button>
                  )}
                  {path && job.status !== "failed" && (
                    <button type="button" className="button button--ghost button--sm" disabled={pending} onClick={() => run(path, [job.stage])}>
                      Run again
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
