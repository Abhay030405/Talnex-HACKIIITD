"use client";

import { useActionState } from "react";

import { updateCriteriaAction } from "@/app/events/[eventId]/actions";
import { CriteriaEditor } from "@/components/forms/CriteriaEditor";
import { SubmitButton } from "@/components/forms/SubmitButton";

/** Edit a fixed-problem event's criteria and weights at any time. Every proof card re-scores at once; nothing is re-tested. */
export function CriteriaWeightsForm({
  eventId,
  criteria,
}: {
  eventId: string;
  criteria: { name: string; description: string; weight: number }[];
}) {
  const [state, action] = useActionState(updateCriteriaAction.bind(null, eventId), {} as { error?: string; saved?: boolean });
  return (
    <form className="form" action={action} id="criteria">
      {state.error && (
        <p className="form-error" role="alert">
          {state.error}
        </p>
      )}
      {state.saved && (
        <p className="notice" role="status">
          Saved. Every proof card&apos;s weighted total now uses these weights.
        </p>
      )}
      <CriteriaEditor initial={criteria} />
      <div className="row">
        <SubmitButton pendingText="Saving…">Save criteria and weights</SubmitButton>
      </div>
    </form>
  );
}
