"use client";

import { useActionState, useEffect, useRef } from "react";

import { addProject, type ProjectFormState } from "@/app/events/[eventId]/actions";
import { Field } from "@/components/forms/Field";
import { SubmitButton } from "@/components/forms/SubmitButton";

const INITIAL: ProjectFormState = {};

/** Adds one team's project to an event. It clears itself after each team, so the next one can be typed in. */
export function ProjectForm({ eventId }: { eventId: string }) {
  const [state, action] = useActionState(addProject.bind(null, eventId), INITIAL);
  const formRef = useRef<HTMLFormElement>(null);

  useEffect(() => {
    if (state.added) formRef.current?.reset();
  }, [state]);

  return (
    <form className="form" action={action} ref={formRef}>
      {state.error && (
        <p className="form-error" role="alert">
          {state.error}
        </p>
      )}
      {state.added && (
        <p className="form-success" role="status">
          {state.added} was added. Add the next team below.
        </p>
      )}

      <Field label="Team name" htmlFor="team_name">
        <input className="input" id="team_name" name="team_name" required maxLength={200} placeholder="Team Rocket" />
      </Field>

      <div className="form-grid">
        <Field label="Demo video" htmlFor="video_url" hint="Where the claims come from in an open-theme event.">
          <input className="input" id="video_url" name="video_url" type="url" placeholder="https://youtu.be/…" />
        </Field>
        <Field label="Live site" htmlFor="live_url" hint="The link TalNex uses like a real person.">
          <input className="input" id="live_url" name="live_url" type="url" placeholder="https://…" />
        </Field>
      </div>

      <Field
        label="Repository"
        htmlFor="repo_url"
        hint="A public GitHub repository. At least one of the three links is needed."
      >
        <input
          className="input"
          id="repo_url"
          name="repo_url"
          type="url"
          placeholder="https://github.com/team/project"
        />
      </Field>

      <div className="form-grid">
        <Field
          label="Team GitHub accounts (optional)"
          htmlFor="team_github_handles"
          hint="Separate with commas. Shows which account wrote each feature; an account is not proof of a person."
        >
          <input className="input" id="team_github_handles" name="team_github_handles" placeholder="alice, bob" />
        </Field>
        <Field
          label="Test login (optional)"
          htmlFor="test_login_ref"
          hint="The name of a login saved in TinyFish Vault. Never type a password here."
        >
          <input
            className="input"
            id="test_login_ref"
            name="test_login_ref"
            autoComplete="off"
            placeholder="team-rocket-demo"
          />
        </Field>
      </div>

      <div className="row">
        <SubmitButton pendingText="Adding…">Add project</SubmitButton>
      </div>
    </form>
  );
}
