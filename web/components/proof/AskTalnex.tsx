"use client";

import Link from "next/link";
import { startTransition, useActionState, useEffect, useRef, useState } from "react";

import { askAction } from "@/app/candidates/[candidateId]/actions";
import { RerunButton } from "@/components/proof/RerunButton";

export interface Ask {
  id: string;
  question: string;
  status: string;
  asked_at: string;
  result: {
    answer?: string;
    action?: { type: "rerun_project" | "rerun_coding" | "change_weight"; project?: string; criterion?: string; weight?: number } | null;
  };
}

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
}: {
  candidateId?: string;
  asks: Ask[];
  projects?: { id: string; name: string }[];
  roleId?: string;
  /** Hackathon mode: ask about one team's project; re-run and weight changes use the event's own actions. */
  project?: {
    ask: (previous: { error?: string }, form: FormData) => Promise<{ error?: string }>;
    rerun: () => Promise<void>;
    criteriaHref: string;
  };
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
