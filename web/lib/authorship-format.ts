// Plain words for authorship proof, shared by the recruiter report and the hackathon card.
// Code is "written by GitHub account X", never by a person, and "could not trace" never counts against anyone.
import type { Authorship, AuthorshipFile, WhoBuiltWhatRow } from "@/lib/types";

export const UNLINKED = "unlinked";

export type AuthorshipView =
  | { kind: "none" }
  | { kind: "traced"; summary: string; files: { label: string; url: string }[]; candidateShare: string | null }
  | { kind: "not_traced"; text: string; files: { label: string; url: string }[] };

/** "src/pay.ts, lines 12–40", or "line 12" for one line. */
export function fileLabel(file: Pick<AuthorshipFile, "path" | "start" | "end">): string {
  if (!file.start) return file.path;
  if (!file.end || file.end === file.start) return `${file.path}, line ${file.start}`;
  return `${file.path}, lines ${file.start}–${file.end}`;
}

/** 0.82 becomes "82%". 0 is a real answer ("0%"), not a missing one. */
export function formatShare(share: number | null | undefined): string | null {
  if (share === null || share === undefined || Number.isNaN(share)) return null;
  return `${Math.round(Math.max(0, Math.min(1, share)) * 100)}%`;
}

export function couldNotTraceText(reason: string | null | undefined): string {
  const why = (reason ?? "").trim();
  return why ? `Could not trace who wrote it: ${why}` : "Could not trace who wrote it";
}

const linkedFiles = (files: AuthorshipFile[] | undefined) =>
  (files ?? []).filter((f) => f.url).map((f) => ({ label: fileLabel(f), url: f.url }));

/** What a claim row shows about who wrote its code. The files are shown even when the history could not be read. */
export function authorshipView(authorship: Authorship | null | undefined): AuthorshipView {
  if (!authorship) return { kind: "none" };
  if (authorship.status !== "traced" || !authorship.summary) {
    return { kind: "not_traced", text: couldNotTraceText(authorship.reason), files: linkedFiles(authorship.files) };
  }
  return {
    kind: "traced",
    summary: authorship.summary,
    files: linkedFiles(authorship.files),
    candidateShare: formatShare(authorship.candidate_share),
  };
}

/** Only rows with features, accounts in name order and unlinked authors last, so the table never reads as a ranking. */
export function whoBuiltWhatRows(rows: WhoBuiltWhatRow[] | null | undefined): WhoBuiltWhatRow[] {
  return (rows ?? [])
    .filter((row) => row.account && row.features.length > 0)
    .sort((a, b) => {
      if (a.account === UNLINKED) return 1;
      if (b.account === UNLINKED) return -1;
      return a.account.localeCompare(b.account, "en", { sensitivity: "base" });
    });
}

/** "@octocat", or words for commits whose email is tied to no GitHub account. */
export function accountLabel(account: string): string {
  return account === UNLINKED ? "Unlinked author (no GitHub account)" : `@${account.replace(/^@/, "")}`;
}
