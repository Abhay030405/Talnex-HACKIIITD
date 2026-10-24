"use client";

import { useActionState, useState } from "react";

import { confirmAction, type ConfirmState } from "@/app/candidates/[candidateId]/actions";
import { Field } from "@/components/forms/Field";
import { SubmitButton } from "@/components/forms/SubmitButton";
import { PlusIcon } from "@/components/ui/Icons";
import { CODING_SITES, MAX_NAME_CHARS, MAX_PROJECTS, profileValue } from "@/lib/confirm-format";
import { PROFILE_KINDS } from "@/lib/profile-links";
import type { CandidateFound, FoundProject } from "@/lib/types";

const INITIAL: ConfirmState = {};
const EMPTY: FoundProject = { name: "", live_url: "", repo_url: "", video_url: "" };

/** Step 2 of a recruiter check: what the resume reader found, for the recruiter to fix, add to or trim. */
export function ConfirmForm({ candidateId, found }: { candidateId: string; found: CandidateFound }) {
  const [state, action] = useActionState(confirmAction.bind(null, candidateId), INITIAL);
  const [rows, setRows] = useState(() => found.projects.map((project, key) => ({ key, project })));
  const [nextKey, setNextKey] = useState(found.projects.length);

  const add = () => {
    setRows((r) => [...r, { key: nextKey, project: EMPTY }]);
    setNextKey((n) => n + 1);
  };
  const remove = (key: number) => setRows((r) => r.filter((row) => row.key !== key));

  return (
    <form className="form" action={action}>
      {state.error && (
        <p className="form-error" role="alert">
          {state.error}
        </p>
      )}

      <section className="stack stack--tight" aria-labelledby="projects-title">
        <h2 className="card__title" id="projects-title">
          Projects to check
        </h2>
        <p className="note">
          Each project needs a name. Add the live link so TalNex can use it, and the code link so it can read the code.
          Remove anything that is not a project. At most {MAX_PROJECTS}.
        </p>
        {rows.length === 0 && <p className="notice">No projects were found on the resume. Add one below.</p>}

        {rows.map((row, index) => (
          <fieldset className="confirm-project fieldset" key={row.key}>
            <legend className="sr-only">Project {index + 1}</legend>
            <input type="hidden" name={`project.${row.key}.id`} defaultValue={row.project.id ?? ""} />
            <div className="form-grid form-grid--wide">
              <Field label="Project name" htmlFor={`name-${row.key}`}>
                <input
                  className="input"
                  id={`name-${row.key}`}
                  name={`project.${row.key}.name`}
                  defaultValue={row.project.name}
                  maxLength={MAX_NAME_CHARS}
                />
              </Field>
              <Field label="Live link" htmlFor={`live-${row.key}`}>
                <input
                  className="input"
                  id={`live-${row.key}`}
                  name={`project.${row.key}.live_url`}
                  defaultValue={row.project.live_url}
                  inputMode="url"
                  placeholder="https://…"
                />
              </Field>
              <Field label="Code link" htmlFor={`repo-${row.key}`}>
                <input
                  className="input"
                  id={`repo-${row.key}`}
                  name={`project.${row.key}.repo_url`}
                  defaultValue={row.project.repo_url}
                  inputMode="url"
                  placeholder="https://github.com/…"
                />
              </Field>
              <Field label="Demo video link" htmlFor={`video-${row.key}`}>
                <input
                  className="input"
                  id={`video-${row.key}`}
                  name={`project.${row.key}.video_url`}
                  defaultValue={row.project.video_url}
                  inputMode="url"
                  placeholder="https://…"
                />
              </Field>
            </div>
            {row.project.bullets && row.project.bullets.length > 0 && (
              <details className="confirm-project__bullets">
                <summary>What the resume says about it</summary>
                <ul>
                  {row.project.bullets.map((bullet, i) => (
                    <li key={i}>{bullet}</li>
                  ))}
                </ul>
              </details>
            )}
            <div className="row">
              <button type="button" className="button button--ghost button--sm" onClick={() => remove(row.key)}>
                Remove this project
              </button>
            </div>
          </fieldset>
        ))}

        <div className="row">
          <button type="button" className="button button--soft" onClick={add} disabled={rows.length >= MAX_PROJECTS}>
            <PlusIcon size={16} />
            Add a project
          </button>
        </div>
      </section>

      <section className="stack stack--tight" aria-labelledby="profiles-title">
        <h2 className="card__title" id="profiles-title">
          Coding profiles
        </h2>
        <p className="note">
          Paste the profile link or just the handle. Leave a box empty to skip that site. TalNex does not check that a
          profile belongs to the candidate.
        </p>
        <div className="form-grid">
          {CODING_SITES.map((site) => (
            <Field key={site.key} label={site.label} htmlFor={`profile-${site.key}`}>
              <input
                className="input"
                id={`profile-${site.key}`}
                name={`profile.${site.key}`}
                placeholder={site.example}
                autoComplete="off"
                defaultValue={profileValue(site.key, found.coding_links, found.coding_handles)}
              />
            </Field>
          ))}
        </div>
      </section>

      <section className="stack">
        <h2 className="panel__title">Profile links</h2>
        <p className="note">
          GitHub, LinkedIn, portfolio and other profile pages from the resume. Fix or add any; leave a box empty to remove
          it. Emails and phone numbers are never kept.
        </p>
        <div className="form-grid">
          {PROFILE_KINDS.map((kind) => (
            <Field key={kind.key} label={kind.label} htmlFor={`link-${kind.key}`}>
              <input
                className="input"
                id={`link-${kind.key}`}
                name={`link.${kind.key}`}
                type="url"
                placeholder={kind.example}
                autoComplete="off"
                defaultValue={found.profile_links?.[kind.key] ?? ""}
              />
            </Field>
          ))}
        </div>
      </section>

      <div className="row">
        <SubmitButton pendingText="Starting…">Start the checks</SubmitButton>
      </div>
    </form>
  );
}
