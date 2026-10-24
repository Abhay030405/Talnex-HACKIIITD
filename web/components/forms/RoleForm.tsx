"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { addResume, createRole } from "@/app/new/role/actions";
import { CriteriaEditor } from "@/components/forms/CriteriaEditor";
import { Field } from "@/components/forms/Field";
import { RoleLevelChoice } from "@/components/forms/RoleLevelChoice";
import { MAX_JOB_TEXT, MAX_PERSON_TEXT, MAX_RESUMES, MAX_ROLE_TITLE } from "@/lib/role-form";
import { ROLE_CHECKS } from "@/lib/types";

type Upload = { name: string; state: "waiting" | "uploading" | "done" | "failed"; error?: string };

const STATE_TEXT: Record<Upload["state"], string> = {
  waiting: "Waiting",
  uploading: "Uploading…",
  done: "Uploaded",
  failed: "Not uploaded",
};

/** Plain text a job description file can be read from in the browser. PDF and Word files are pasted instead. */
const TEXT_FILE = /\.(txt|md|markdown|text)$/i;

/**
 * A role (job opening) and any number of resumes for it. The role is saved first, then each resume is sent on its
 * own, so a large batch never hits the upload size limit and the recruiter sees each one arrive.
 */
export function RoleForm() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [uploads, setUploads] = useState<Upload[]>([]);
  const [busy, setBusy] = useState(false);
  const [jobText, setJobText] = useState("");

  async function readJobFile(file: File | undefined) {
    if (!file) return;
    if (!TEXT_FILE.test(file.name)) {
      setError("Only a .txt or .md job description can be read here. For a PDF or Word file, paste its text below.");
      return;
    }
    setError(null);
    setJobText((await file.text()).slice(0, MAX_JOB_TEXT));
  }

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const files = form.getAll("resumes").filter((f): f is File => f instanceof File && f.size > 0);
    if (files.length === 0) return setError("Choose at least one resume (PDF).");
    if (files.length > MAX_RESUMES) return setError(`Upload at most ${MAX_RESUMES} resumes at a time.`);
    form.delete("resumes");
    setError(null);
    setBusy(true);

    const role = await createRole(form);
    if (!role.ok) {
      setBusy(false);
      return setError(role.error);
    }
    const list: Upload[] = files.map((f) => ({ name: f.name, state: "waiting" }));
    setUploads([...list]);
    for (let i = 0; i < files.length; i++) {
      list[i] = { ...list[i], state: "uploading" };
      setUploads([...list]);
      const one = new FormData();
      one.set("resume", files[i]);
      one.set("label", files[i].name.replace(/\.pdf$/i, ""));
      const done = await addResume(role.value, one);
      list[i] = done.ok ? { ...list[i], state: "done" } : { ...list[i], state: "failed", error: done.error };
      setUploads([...list]);
    }
    router.push(`/roles/${role.value}`);
  }

  const finished = uploads.filter((u) => u.state === "done" || u.state === "failed").length;

  return (
    <form className="form" onSubmit={submit}>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}

      <Field label="Role title" htmlFor="title" hint="For example: Backend intern, summer 2027.">
        <input className="input" id="title" name="title" required maxLength={MAX_ROLE_TITLE} aria-describedby="title-hint" />
      </Field>

      <Field
        label="Job description"
        htmlFor="job_description"
        hint="Paste it, or load a .txt or .md file. TalNex judges every project against it."
      >
        <input
          className="input input--file"
          type="file"
          accept=".txt,.md,.markdown,text/plain,text/markdown"
          aria-label="Load the job description from a text file"
          onChange={(e) => readJobFile(e.target.files?.[0])}
        />
        <textarea
          className="input textarea"
          id="job_description"
          name="job_description"
          rows={8}
          maxLength={MAX_JOB_TEXT}
          value={jobText}
          onChange={(e) => setJobText(e.target.value)}
          aria-describedby="job_description-hint"
        />
      </Field>

      <Field label="The kind of person you want (optional)" htmlFor="person_wanted" hint="In your own words.">
        <textarea
          className="input textarea"
          id="person_wanted"
          name="person_wanted"
          rows={3}
          maxLength={MAX_PERSON_TEXT}
          placeholder="Ships small, tested changes; comfortable owning a backend service end to end."
          aria-describedby="person_wanted-hint"
        />
      </Field>

      <Field label="Must-have skills (optional)" htmlFor="skills" hint="Separate them with commas.">
        <input className="input" id="skills" name="skills" placeholder="Go, PostgreSQL, REST APIs" aria-describedby="skills-hint" />
      </Field>

      <RoleLevelChoice />

      <CriteriaEditor />

      <fieldset className="field fieldset">
        <legend className="field__label">Checks to run</legend>
        <span className="field__hint">Leave everything ticked for the full check. A check you leave out is shown as not run.</span>
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

      <Field
        label="Resumes (PDF)"
        htmlFor="resumes"
        hint={`One or many, up to ${MAX_RESUMES} at a time, 5 MB each. Every file is deleted after its report.`}
      >
        <input
          className="input input--file"
          id="resumes"
          name="resumes"
          type="file"
          accept="application/pdf,.pdf"
          multiple
          required
          aria-describedby="resumes-hint"
        />
      </Field>

      <label className="check-line">
        <input type="checkbox" name="auto_confirm" defaultChecked />
        <span>Start the checks on what TalNex finds, without asking me to confirm each resume</span>
      </label>

      {uploads.length > 0 && (
        <div className="upload-list" aria-live="polite">
          <span className="meta">
            {finished} of {uploads.length} resumes sent
          </span>
          <ul className="report-list">
            {uploads.map((u, i) => (
              <li key={i} className={`upload-list__item upload-list__item--${u.state}`}>
                {u.name}: {STATE_TEXT[u.state]}
                {u.error ? ` (${u.error})` : ""}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="row">
        <button className="button button--primary" type="submit" disabled={busy}>
          {busy ? "Working…" : "Save the role and read the resumes"}
        </button>
      </div>
    </form>
  );
}
