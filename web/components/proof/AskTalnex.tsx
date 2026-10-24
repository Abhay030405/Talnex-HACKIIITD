"use client";

import Link from "next/link";
import { startTransition, useActionState, useEffect, useRef, useState } from "react";

import { askAction } from "@/app/candidates/[candidateId]/actions";
import { CustomTestButton } from "@/components/proof/CustomTestButton";
import { RerunButton } from "@/components/proof/RerunButton";

export interface Ask {
  id: string;
  question: string;
  status: string;
  asked_at: string;
  result: {
    answer?: string;
    action?: {
      type: "rerun_project" | "rerun_coding" | "change_weight" | "custom_test";
      project?: string;
      instruction?: string;
      criterion?: string;
      weight?: number;
    } | null;
    /** Fresh facts the answer looked up (GitHub, the live site, a coding profile), with when. */
    sources?: { tool: string; what: string; at: string }[];
  };
}

const SOURCE_NAME: Record<string, string> = { github: "GitHub", fetch_page: "Live site", coding_profile: "Coding profile" };

/** A one-off test the reviewer asked for (job custom_test). Its result never changes a score. */
export interface CustomTest {
  id: string;
  instruction: string;
  status: string;
  asked_at: string;
  project?: string;
  result: {
    verdict?: string;
    observed?: string;
    steps?: { action: string; observed: string | null; proof_url?: string }[];
  };
}

const VERDICT_BADGE: Record<string, { text: string; className: string }> = {
  works: { text: "Works", className: "badge badge--success" },
  partly_works: { text: "Partly works", className: "badge badge--warning" },
  broken: { text: "Broken", className: "badge badge--danger" },
  could_not_test: { text: "Could not test", className: "badge badge--neutral" },
};

const CANDIDATE_STARTERS = [
  "Summarise this candidate's strengths and gaps",
  "Why did the broken features fail?",
  "What should I ask in the interview?",
  "How well do they fit the role?",
];

const PROJECT_STARTERS = [
  "Summarise what works and what does not",
  "Why did the broken features fail?",
  "How well does it meet the brief?",
  "Which criteria are weakest?",
];

/**
 * Ask TalNex: a chat about this candidate, answered from the proof report. It remembers the conversation. A suggested
 * action (re-test, re-run, change a weight) is a button inside the answer; nothing paid starts until you press it.
 */
export function AskTalnex({
  candidateId,
  asks,
  projects = [],
  roleId,
  project,
  customTests = [],
}: {
  candidateId?: string;
  asks: Ask[];
  projects?: { id: string; name: string }[];
  roleId?: string;
  /** Hackathon mode: ask about one team's project; re-run and weight changes use the event's own actions. */
  project?: {
    id: string;
    name: string;
    liveHref: string;
    ask: (previous: { error?: string }, form: FormData) => Promise<{ error?: string }>;
    rerun: () => Promise<void>;
    criteriaHref: string;
  };
  customTests?: CustomTest[];
}) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const [state, action, sending] = useActionState(
    project ? project.ask : askAction.bind(null, candidateId ?? ""),
    {} as { error?: string },
  );
  const STARTERS = project ? PROJECT_STARTERS : CANDIDATE_STARTERS;
  const end = useRef<HTMLDivElement>(null);
  const thread = [...asks].reverse(); // oldest first, like any chat
  const thinking = asks.some((a) => a.status !== "done" && a.status !== "failed");
  const tests = [...customTests].sort((a, b) => a.asked_at.localeCompare(b.asked_at));

  /** Where a proposed custom test runs, and which live view to open for it. */
  function testTarget(name?: string) {
    if (project) return { target: { kind: "project" as const, id: project.id }, name: project.name, liveHref: project.liveHref };
    const found = projects.find((p) => p.name === name);
    return found && candidateId
      ? { target: { kind: "candidate_project" as const, id: found.id }, name: found.name, liveHref: `/candidates/${candidateId}/live` }
      : null;
  }

  useEffect(() => {
    if (open) end.current?.scrollIntoView({ block: "end" });
  }, [open, asks.length, thinking]);

  function send(text: string) {
    const form = new FormData();
    form.set("question", text);
    setDraft("");
    startTransition(() => action(form));
  }

  return (
    <>
      <button type="button" className="chat-launcher button button--primary" onClick={() => setOpen(!open)} aria-expanded={open}>
        {open ? "Close chat" : "Ask TalNex"}
      </button>
      {open && (
        <aside className="chat" aria-label={project ? "Ask TalNex about this project" : "Ask TalNex about this candidate"}>
          <header className="chat__head">
            <strong>Ask TalNex</strong>
            <span className="meta">Answers come from this report&apos;s proof only</span>
          </header>
          <div className="chat__thread" aria-live="polite">
            {thread.length === 0 && (
              <div className="chat__bubble chat__bubble--ai">
                {project
                  ? "Ask me anything about this team's proof card: why a feature failed, how it meets the brief, which criteria are weakest. I can also re-check the project when you ask."
                  : "Ask me anything about this candidate's report: why a feature failed, what to ask in the interview, how they fit the role. I can also re-test a project or re-run the coding checks when you ask."}
              </div>
            )}
            {thread.map((a) => {
              const act = a.result?.action;
              const target = act?.type === "rerun_project" ? projects.find((p) => p.name === act.project) : undefined;
              const done = a.status === "done";
              return (
                <div className="chat__pair" key={a.id}>
                  <div className="chat__bubble chat__bubble--me">{a.question}</div>
                  <div className={`chat__bubble chat__bubble--ai${done ? "" : " chat__bubble--waiting"}`}>
                    {done ? a.result?.answer : a.status === "failed" ? "I could not answer that one. Try asking again." : "TalNex is thinking…"}
                    {done && (a.result?.sources ?? []).length > 0 && (
                      <div className="chat__sources">
                        {(a.result.sources ?? []).map((s, i) => (
                          <span className="chat__source" key={i} title={`Checked ${new Date(s.at).toLocaleString()}`}>
                            {SOURCE_NAME[s.tool] ?? s.tool}: {s.what}
                          </span>
                        ))}
                      </div>
                    )}
                    {target && candidateId && (
                      <div className="chat__action">
                        <RerunButton candidateId={candidateId} projectId={target.id}>
                          Re-test {target.name}
                        </RerunButton>
                      </div>
                    )}
                    {project && act?.type === "rerun_project" && (
                      <form className="chat__action" action={project.rerun}>
                        <button type="submit" className="button button--ghost button--sm">
                          Check this project again
                        </button>
                      </form>
                    )}
                    {candidateId && act?.type === "rerun_coding" && (
                      <div className="chat__action">
                        <RerunButton candidateId={candidateId}>Re-run coding checks</RerunButton>
                      </div>
                    )}
                    {act?.type === "custom_test" && act.instruction && (() => {
                      const where = testTarget(act.project);
                      return where ? (
                        <CustomTestButton
                          target={where.target}
                          projectName={where.name}
                          instruction={act.instruction}
                          liveHref={where.liveHref}
                        />
                      ) : null;
                    })()}
                    {act?.type === "change_weight" && (roleId || project) && (
                      <div className="chat__action">
                        <Link className="button button--ghost button--sm" href={project ? project.criteriaHref : `/roles/${roleId}/settings`}>
                          Set {act.criterion} to weight {act.weight}
                        </Link>
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
            {tests.map((t) => {
              const badge = VERDICT_BADGE[t.result?.verdict ?? ""];
              const done = t.status === "done";
              return (
                <div className="chat__pair" key={t.id}>
                  <div className="chat__bubble chat__bubble--me">Custom test{t.project ? ` on ${t.project}` : ""}: {t.instruction}</div>
                  <div className={`chat__bubble chat__bubble--ai${done ? "" : " chat__bubble--waiting"}`}>
                    {!done && t.status !== "failed" && "Running the test… watch it in the live view."}
                    {t.status === "failed" && "The test could not run this time. It does not count against anyone."}
                    {done && (
                      <>
                        {badge && <span className={badge.className}>{badge.text}</span>} {t.result?.observed}
                        <span className="meta"> (a one-off test: it does not change any score)</span>
                        <div className="chat__shots">
                          {(t.result?.steps ?? [])
                            .filter((s) => s.proof_url)
                            .map((s, i) => (
                              // A short-lived storage link: Next's image optimiser would cache it past its life.
                              // eslint-disable-next-line @next/next/no-img-element
                              <img key={i} className="chat__shot" src={s.proof_url} alt={s.action} title={s.action} loading="lazy" />
                            ))}
                        </div>
                      </>
                    )}
                  </div>
                </div>
              );
            })}
            <div ref={end} />
          </div>
          {thread.length === 0 && (
            <div className="chat__starters">
              {STARTERS.map((s) => (
                <button key={s} type="button" className="chat__chip" onClick={() => send(s)} disabled={sending}>
                  {s}
                </button>
              ))}
            </div>
          )}
          {state.error && (
            <p className="form-error" role="alert">
              {state.error}
            </p>
          )}
          <form
            className="chat__compose"
            onSubmit={(e) => {
              e.preventDefault();
              if (draft.trim()) send(draft.trim());
            }}
          >
            <textarea
              className="input chat__input"
              value={draft}
              rows={2}
              maxLength={1000}
              placeholder="Ask a question, or say “re-test the second project”"
              aria-label="Your message"
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  if (draft.trim()) send(draft.trim());
                }
              }}
            />
            <button type="submit" className="button button--primary" disabled={sending || !draft.trim()}>
              {sending ? "…" : "Send"}
            </button>
          </form>
        </aside>
      )}
    </>
  );
}
