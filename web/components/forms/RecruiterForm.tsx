"use client";

import { useActionState } from "react";

import { createCandidate, type FormState } from "@/app/new/recruiter/actions";
import { Field } from "@/components/forms/Field";
import { RoleLevelChoice } from "@/components/forms/RoleLevelChoice";
import { SubmitButton } from "@/components/forms/SubmitButton";
import { MAX_LABEL_LENGTH } from "@/lib/resume";
import { ROLE_CHECKS } from "@/lib/types";

const INITIAL: FormState = {};

/** Step 1 of 2: the resume and the role level. Step 2, confirming what was found, opens once the resume is read. */
export function RecruiterForm() {
  const [state, action] = useActionState(createCandidate, INITIAL);

  return (
    <form className="form" action={action}>
      {state.error && (
        <p className="form-error" role="alert">
          {state.error}
        </p>
      )}

      <Field
        label="Resume (PDF)"
        htmlFor="resume"
        hint="Up to 5 MB. TalNex reads the projects and coding profiles on it. The file is deleted after the report."
      >
        <input
          className="input input--file"
          id="resume"
          name="resume"
          type="file"
          accept="application/pdf,.pdf"
          required
          aria-describedby="resume-hint"
        />
      </Field>

      <RoleLevelChoice />

      <fieldset className="field fieldset">
        <legend className="field__label">Checks to run</legend>
        <span className="field__hint">All ticked is the full check. Untick any for a partial check; a check left out is shown as not run.</span>
        <input type="hidden" name="checks_shown" value="1" />
        <div className="choice-grid">
          {ROLE_CHECKS.map((check) => (
            <label className="choice" key={check.value}>
              <input className="choice__input" type="checkbox" name="checks" value={check.value} defaultChecked />
              <span className="choice__title">{check.label}</span>
              <span className="choice__text">{check.hint}</span>
            </label>
          ))}
        </div>
      </fieldset>

      <Field label="Name for your list (optional)" htmlFor="label" hint="Only you see it.">
        <input
          className="input"
          id="label"
          name="label"
          maxLength={MAX_LABEL_LENGTH}
          autoComplete="off"
          placeholder="Asha, backend role"
          aria-describedby="label-hint"
        />
      </Field>

      <div className="row">
        <SubmitButton pendingText="Uploading…">Read the resume</SubmitButton>
      </div>
    </form>
  );
}
