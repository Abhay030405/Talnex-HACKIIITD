"use client";

import { useState } from "react";

import { PlusIcon } from "@/components/ui/Icons";
import { MAX_CRITERIA } from "@/lib/event-form";

let nextKey = 0;
type Row = { key: number; name?: string; description?: string; weight?: number };
const newRow = (from: Omit<Row, "key"> = {}): Row => ({ key: nextKey++, ...from });

/** Feature groups TalNex scores in; a criterion with one of these names weighs those features. */
const GROUPS = ["Core", "Logic", "UI", "Access", "Reliability", "Edge cases", "Setup", "Engineering"];

/** The scoring criteria of a fixed-problem event: a name, an optional description and a weight for each. */
export function CriteriaEditor({ initial = [] }: { initial?: { name: string; description: string; weight: number }[] }) {
  const [rows, setRows] = useState(() => (initial.length ? initial.map((c) => newRow(c)) : [newRow(), newRow(), newRow()]));

  return (
    <fieldset className="field fieldset">
      <legend className="field__label">Scoring criteria</legend>
      <span className="field__hint">
        The groups each project is scored in. Weights are shown as you give them; the total is labelled as weighted. A
        criterion called Engineering weighs how the repository is built (engineering quality).
      </span>

      <datalist id="criteria-groups">
        {GROUPS.map((g) => (
          <option key={g} value={g} />
        ))}
      </datalist>
      <div className="criteria">
        {rows.map((row, index) => (
          <div className="criteria__row" key={row.key}>
            <input
              className="input"
              name="criterion_name"
              list="criteria-groups"
              defaultValue={row.name}
              aria-label={`Criterion ${index + 1} name`}
              placeholder={index === 0 ? "Core flow works" : "Criterion name"}
            />
            <input
              className="input"
              name="criterion_description"
              defaultValue={row.description}
              aria-label={`Criterion ${index + 1} description`}
              placeholder="What it means (optional)"
            />
            <input
              className="input"
              name="criterion_weight"
              defaultValue={row.weight}
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
