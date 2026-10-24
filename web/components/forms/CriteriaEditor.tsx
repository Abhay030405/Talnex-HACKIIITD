"use client";

import { useState } from "react";

import { PlusIcon } from "@/components/ui/Icons";
import { MAX_CRITERIA } from "@/lib/event-form";

let nextKey = 0;
const newRow = () => ({ key: nextKey++ });

/** The scoring criteria of a fixed-problem event: a name, an optional description and a weight for each. */
export function CriteriaEditor() {
  const [rows, setRows] = useState(() => [newRow(), newRow(), newRow()]);

  return (
    <fieldset className="field fieldset">
      <legend className="field__label">Scoring criteria</legend>
      <span className="field__hint">
        The groups each project is scored in. Weights are shown as you give them; the total is labelled as weighted.
      </span>

      <div className="criteria">
        {rows.map((row, index) => (
          <div className="criteria__row" key={row.key}>
            <input
              className="input"
              name="criterion_name"
              aria-label={`Criterion ${index + 1} name`}
              placeholder={index === 0 ? "Core flow works" : "Criterion name"}
            />
            <input
              className="input"
              name="criterion_description"
              aria-label={`Criterion ${index + 1} description`}
              placeholder="What it means (optional)"
            />
            <input
              className="input"
              name="criterion_weight"
              type="number"
              min="0.1"
              step="0.1"
              inputMode="decimal"
              aria-label={`Criterion ${index + 1} weight`}
              placeholder="Weight"
            />
            <button
              type="button"
              className="button button--ghost button--sm"
              onClick={() => setRows((r) => r.filter((x) => x.key !== row.key))}
              disabled={rows.length === 1}
              aria-label={`Remove criterion ${index + 1}`}
            >
              Remove
            </button>
          </div>
        ))}
      </div>

      {rows.length < MAX_CRITERIA && (
        <button
          type="button"
          className="button button--soft button--sm"
          onClick={() => setRows((r) => [...r, newRow()])}
        >
          <PlusIcon size={16} />
          Add a criterion
        </button>
      )}
    </fieldset>
  );
}
