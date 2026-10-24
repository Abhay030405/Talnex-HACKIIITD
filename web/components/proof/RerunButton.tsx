"use client";

import { useState, useTransition } from "react";

import { rerunAction } from "@/app/candidates/[candidateId]/actions";

/** Starts a re-run (one project, or the coding checks) and opens the live view to watch it. */
export function RerunButton({
  candidateId,
  projectId,
  children,
}: {
  candidateId: string;
  projectId?: string;
  children: React.ReactNode;
}) {
  const [pending, start] = useTransition();
  const [error, setError] = useState<string | null>(null);
  return (
    <span className="row">
      <button
        type="button"
        className="button button--ghost button--sm"
        disabled={pending}
        onClick={() =>
          start(async () => {
            const result = await rerunAction(candidateId, projectId ? { kind: "project", projectId } : { kind: "coding" });
            if (result?.error) setError(result.error);
          })
        }
      >
        {pending ? "Starting…" : children}
      </button>
      {error && (
        <span className="form-error" role="alert">
          {error}
        </span>
      )}
    </span>
  );
}
