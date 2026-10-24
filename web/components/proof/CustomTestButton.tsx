"use client";

import { useState, useTransition } from "react";

import { startCustomTestAction } from "@/app/custom-test-actions";

/** The planned custom test and a button to run it. Nothing runs until it is pressed: each run uses browser credits. */
export function CustomTestButton({
  target,
  projectName,
  instruction,
  liveHref,
}: {
  target: { kind: "candidate_project" | "project"; id: string };
  projectName: string;
  instruction: string;
  liveHref: string;
}) {
  const [pending, start] = useTransition();
  const [error, setError] = useState<string | null>(null);
  return (
    <div className="chat__action stack stack--tight">
      <span className="meta">
        Planned test on {projectName}: {instruction}
      </span>
      <button
        type="button"
        className="button button--primary button--sm"
        disabled={pending}
        onClick={() =>
          start(async () => {
            const result = await startCustomTestAction(target, instruction, liveHref);
            if (result?.error) setError(result.error);
          })
        }
      >
        {pending ? "Starting…" : "Run this test"}
      </button>
      {error && (
        <span className="form-error" role="alert">
          {error}
        </span>
      )}
    </div>
  );
}
