"use client";

import { useActionState, useState } from "react";

import { createEvent, type FormState } from "@/app/new/hackathon/actions";
import { CriteriaEditor } from "@/components/forms/CriteriaEditor";
import { Field } from "@/components/forms/Field";
import { RoleLevelChoice } from "@/components/forms/RoleLevelChoice";
import { SubmitButton } from "@/components/forms/SubmitButton";
import type { EventMode } from "@/lib/types";

const INITIAL: FormState = {};

const MODES: { value: EventMode; title: string; text: string }[] = [
  { value: "open_theme", title: "Open theme", text: "Teams build anything. TalNex reads what each team built from its repository." },
  { value: "fixed_problem", title: "Fixed problem", text: "One problem for everyone, scored on your own criteria." },
];

export function HackathonForm() {
  const [state, action] = useActionState(createEvent, INITIAL);
  const [mode, setMode] = useState<EventMode>("open_theme");

  return (
    <form className="form" action={action}>
      {state.error && (
        <p className="form-error" role="alert">
          {state.error}
        </p>
      )}

      <Field label="Event name" htmlFor="name">
        <input className="input" id="name" name="name" required maxLength={200} placeholder="Campus Hack 2026" />
      </Field>

      <fieldset className="field fieldset">
        <legend className="field__label">Event type</legend>
        <div className="choice-grid">
          {MODES.map((m) => (
            <label className="choice" key={m.value}>
              <input
                className="choice__input"
                type="radio"
                name="mode"
                value={m.value}
                checked={mode === m.value}
                onChange={() => setMode(m.value)}
              />
              <span className="choice__title">{m.title}</span>
              <span className="choice__text">{m.text}</span>
            </label>
          ))}
        </div>
      </fieldset>

      {mode === "fixed_problem" && <CriteriaEditor />}

      <div className="form-grid">
        <Field label="Starts on" htmlFor="starts_on" hint="Code pushed before this day is flagged, never subtracted.">
          <input
            className="input"
            id="starts_on"
            name="starts_on"
            type="date"
            required
            aria-describedby="starts_on-hint"
          />
        </Field>
        <Field label="Ends on" htmlFor="ends_on">
          <input className="input" id="ends_on" name="ends_on" type="date" required />
        </Field>
      </div>

      <Field
        label="Sponsor tools (optional)"
        htmlFor="sponsor_tools"
        hint="Separate with commas. TalNex checks that a team really used them."
      >
        <input
          className="input"
          id="sponsor_tools"
          name="sponsor_tools"
          placeholder="Stripe, Twilio"
          aria-describedby="sponsor_tools-hint"
        />
      </Field>

      <RoleLevelChoice />

      <div className="row">
        <SubmitButton pendingText="Creating…">Create event</SubmitButton>
      </div>
    </form>
  );
}
