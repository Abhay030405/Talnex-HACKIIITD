import { authorshipView } from "@/lib/authorship-format";
import type { Authorship } from "@/lib/types";

function Files({ files }: { files: { label: string; url: string }[] }) {
  if (files.length === 0) return null;
  return (
    <ul className="authorship__files" aria-label="The code behind this claim">
      {files.map((file) => (
        <li key={file.url}>
          <a className="authorship__file" href={file.url} target="_blank" rel="noopener noreferrer">
            {file.label}
          </a>
        </li>
      ))}
    </ul>
  );
}

/** Who wrote the code behind one claim: a GitHub account, never a person. Not tracing it is neutral. */
export function AuthorshipLine({ authorship }: { authorship?: Authorship | null }) {
  const view = authorshipView(authorship);
  if (view.kind === "none") return null;
  if (view.kind === "not_traced") {
    return (
      <div className="authorship authorship--untraced">
        <span>{view.text}. This does not count against anyone.</span>
        <Files files={view.files} />
      </div>
    );
  }
  return (
    <div className="authorship">
      <span className="authorship__summary">{view.summary}</span>
      {view.candidateShare !== null && (
        <span className="meta">The candidate&apos;s account wrote {view.candidateShare} of these lines.</span>
      )}
      <Files files={view.files} />
    </div>
  );
}
