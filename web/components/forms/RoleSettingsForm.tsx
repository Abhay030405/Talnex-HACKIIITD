"use client";

import { useActionState } from "react";

import { updateRole, type SettingsState } from "@/app/roles/[roleId]/settings/actions";
import { CriteriaEditor } from "@/components/forms/CriteriaEditor";
import { Field } from "@/components/forms/Field";
import { RoleLevelChoice } from "@/components/forms/RoleLevelChoice";
import { SubmitButton } from "@/components/forms/SubmitButton";
import { MAX_JOB_TEXT, MAX_PERSON_TEXT, MAX_ROLE_TITLE } from "@/lib/role-form";
import { ROLE_CHECKS, type JobRole } from "@/lib/types";

/** Edit a role at any time, before or after results. Weights re-score every candidate at once; nothing is re-tested. */
export function RoleSettingsForm({ role }: { role: JobRole }) {
  const [state, action] = useActionState<SettingsState, FormData>(updateRole.bind(null, role.id), {});
  const allOn = Object.keys(role.checks).length === 0;

  return (
    <form className="form" action={action}>
      {state.error && (
        <p className="form-error" role="alert">
          {state.error}
        </p>
      )}
      {state.saved && (
        <p className="notice" role="status">
          Saved. Every candidate&apos;s weighted score now uses these weights.
        </p>
      )}
      <Field label="Role title" htmlFor="title">
        <input className="input" id="title" name="title" required maxLength={MAX_ROLE_TITLE} defaultValue={role.title} />
      </Field>
      <Field label="Job description" htmlFor="job_description">
        <textarea className="input textarea" id="job_description" name="job_description" rows={8} maxLength={MAX_JOB_TEXT} defaultValue={role.job_description} />
      </Field>
      <Field label="The kind of person you want" htmlFor="person_wanted">
        <textarea className="input textarea" id="person_wanted" name="person_wanted" rows={3} maxLength={MAX_PERSON_TEXT} defaultValue={role.person_wanted} />
      </Field>
      <Field label="Must-have skills" htmlFor="skills" hint="Separate them with commas.">
        <input className="input" id="skills" name="skills" defaultValue={role.skills.join(", ")} aria-describedby="skills-hint" />
      </Field>
      <RoleLevelChoice defaultValue={role.role_level} />
      <CriteriaEditor initial={(role.criteria ?? []).map((c) => ({ ...c, description: c.description ?? "" }))} />
      <fieldset className="field fieldset">
        <legend className="field__label">Checks to run</legend>
        <span className="field__hint">Applies to resumes uploaded from now on.</span>
        <div className="choice-grid">
          {ROLE_CHECKS.map((check) => (
            <label className="choice" key={check.value}>
              <input className="choice__input" type="checkbox" name="checks" value={check.value} defaultChecked={allOn || role.checks[check.value] !== false} />
              <span className="choice__title">{check.label}</span>
              <span className="choice__text">{check.hint}</span>
            </label>
          ))}
        </div>
      </fieldset>
      <label className="check-line">
        <input type="checkbox" name="auto_confirm" defaultChecked={role.auto_confirm} />
        <span>Start the checks on what TalNex finds, without asking me to confirm each resume</span>
      </label>
      <div className="row">
        <SubmitButton pendingText="Saving…">Save the role</SubmitButton>
      </div>
    </form>
  );
}
