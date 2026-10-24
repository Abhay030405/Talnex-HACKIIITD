"use client";

import { useCallback, useEffect, useId, useReducer, useRef, useState, type FormEvent } from "react";

import { TourBrowser } from "@/components/tour/TourBrowser";
import { ArrowIcon } from "@/components/ui/Icons";
import {
  MAX_TOUR_QUESTION_CHARS,
  TOUR_EVENT_KINDS,
  TOUR_LABEL,
  codeLabel,
  emptyTourLive,
  reduceTour,
  tourPageUrl,
  workingWords,
  type LiveSay,
  type Tour,
  type TourEvent,
  type TourLive,
  type TourMessage,
  type TourProof,
  type TourSay,
} from "@/lib/tour";
import type { WalkthroughSubject } from "@/lib/types";

const POLL_EVERY_MS = 3000;

type Action = { type: "event"; kind: string; event: TourEvent; tourId: string } | { type: "reset" };

function reducer(state: TourLive, action: Action): TourLive {
  return action.type === "reset" ? emptyTourLive() : reduceTour(state, action.kind, action.event, action.tourId);
}

async function readJson<T>(response: Response): Promise<T & { error?: string }> {
  try {
    return (await response.json()) as T & { error?: string };
  } catch {
    return { error: response.ok ? undefined : "Something went wrong. Please try again." } as T & { error?: string };
  }
}

/** Ways to start, shown before the first question. They fit any project: the guide finds the feature itself. */
const STARTERS = [
  "Walk me through how the main feature works",
  "How does this project handle its data?",
  "Show me what a visitor can do on the site",
];

const isOpen = (m: TourMessage) => m.status === "queued" || m.status === "working";

/** One sentence of the guide: its words, the code it points to, and a plain note when it could not be shown. */
function Say({ text, proof, note }: { text: string; proof: TourProof[]; note?: string | null }) {
  const code = proof.filter((p) => p.kind === "code");
  return (
    <li className="tour-say">
      <p className="tour-say__text">{text}</p>
      {code.length > 0 && (
        <span className="tour-say__refs">
          {code.map((p, i) =>
            p.url ? (
              <a key={i} className="tour-say__ref" href={p.url} target="_blank" rel="noreferrer">
                {codeLabel(p)}
              </a>
            ) : (
              <span key={i} className="tour-say__ref">
                {codeLabel(p)}
              </span>
            ),
          )}
        </span>
      )}
      {note && <p className="tour-say__note">{note}</p>}
    </li>
  );
}

function Answer({ says }: { says: (TourSay | LiveSay)[] }) {
  return (
    <ol className="tour-says">
      {says.map((s, i) => (
        <Say
          key={i}
          text={s.text}
          proof={"snippets" in s && s.snippets.length > 0 ? s.snippets : s.proof}
          note={s.note}
        />
      ))}
    </ol>
  );
}

/**
 * The walk-through: a chat on the left, the live site on the right, the code under it. The user asks how a feature was
 * built; the guide reads the code, explains each step, and shows it on the live site. Everything the guide says comes
 * from the code and is labelled as an explanation, never a score.
 */
export function TourWorkspace({
  subject,
  subjectId,
  parentId,
  siteUrl,
  hasRepo,
  initial,
}: {
  subject: WalkthroughSubject;
  subjectId: string;
  parentId: string;
  siteUrl: string | null;
  hasRepo: boolean;
  initial: Tour | null;
}) {
  const inputId = useId();
  const [tour, setTour] = useState<Tour | null>(initial);
  const [live, dispatch] = useReducer(reducer, undefined, emptyTourLive);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const tourId = tour?.id ?? null;
  const tourRef = useRef(tourId);
  tourRef.current = tourId;
  const messages = tour?.messages ?? [];
  const working = messages.some(isOpen);

  const refresh = useCallback(async () => {
    const id = tourRef.current;
    if (!id) return;
    const response = await fetch(`/api/tours/${encodeURIComponent(id)}`, { cache: "no-store" });
    if (response.ok) setTour((await response.json()) as Tour);
  }, []);

  // The stream of this project carries every tour on it; the reducer keeps only this chat's events.
  useEffect(() => {
    if (!tourId) return;
    const source = new EventSource(`/api/live/${encodeURIComponent(subject)}/${encodeURIComponent(subjectId)}`);
    source.addEventListener("replay.start", () => dispatch({ type: "reset" }));
    for (const kind of TOUR_EVENT_KINDS) {
      source.addEventListener(kind, (message) => {
        try {
          const event = JSON.parse((message as MessageEvent).data) as TourEvent;
          dispatch({ type: "event", kind, event, tourId });
          if (kind === "tour.done" && event.tour_id === tourId) void refresh();
        } catch {
          // A message that is not JSON is skipped; the stream goes on.
        }
      });
    }
    return () => source.close();
  }, [subject, subjectId, tourId, refresh]);

  // If the stream is quiet or down, asking every few seconds still shows the finished answer.
  useEffect(() => {
    if (!working) return;
    const timer = setInterval(() => void refresh(), POLL_EVERY_MS);
    return () => clearInterval(timer);
  }, [working, refresh]);

  async function send(text: string) {
    setError(null);
    setBusy(true);
    try {
      const response = await fetch(tourId ? `/api/tours/${encodeURIComponent(tourId)}` : "/api/tours", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(tourId ? { question: text } : { subject, id: subjectId, question: text }),
      });
      const data = await readJson<{ id: string; message_id: string }>(response);
      if (!response.ok || !data.id) return setError(data.error ?? "The question could not be sent. Please try again.");
      const asked: TourMessage = {
        id: data.message_id, question: text, status: "queued", answer: null, error: null,
        created_at: new Date().toISOString(), answered_at: null,
      };
      setTour((t) => ({ id: data.id, subject: t?.subject ?? { kind: subject, id: subjectId }, messages: [...(t?.messages ?? []), asked] }));
      setQuestion("");
      if (!tourId) window.history.replaceState(null, "", tourPageUrl(subject, subjectId, parentId, data.id));
    } catch {
      setError("Cannot reach the website. Check your connection and try again.");
    } finally {
      setBusy(false);
    }
  }

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const text = question.trim();
    if (!text) return setError("Type a question first.");
    void send(text.slice(0, MAX_TOUR_QUESTION_CHARS));
  }

  const words = workingWords(live);

  return (
    <div className="tour">
      <section className="tour__chat" aria-label="Chat with the guide">
        <div className="tour__messages" aria-live="polite">
          {messages.length === 0 && (
            <div className="tour-welcome">
              <span className="tour-bot__avatar tour-welcome__mark" aria-hidden="true">T</span>
              <h2 className="tour-welcome__title">How can I walk you through this project?</h2>
              <p className="tour-welcome__text">
                Ask how a feature was built. I read the code, explain it step by step, and show it on the live site.
                {!hasRepo && " This project has no code link, so I can only show the live site."}
              </p>
              <div className="tour-welcome__starters">
                {STARTERS.map((text) => (
                  <button key={text} type="button" className="tour-chip" disabled={busy || working} onClick={() => void send(text)}>
                    {text}
                  </button>
                ))}
              </div>
            </div>
          )}
          {messages.map((m) => (
            <div key={m.id} className="tour__turn">
              <p className="tour__question">{m.question}</p>
              <div className="tour-bot">
                <span className="tour-bot__avatar" aria-hidden="true">T</span>
                <div className="tour-bot__body">
                  {m.answer ? (
                    <>
                      <Answer says={m.answer.say} />
                      <p className="tour__label">{m.answer.label || TOUR_LABEL}</p>
                    </>
                  ) : m.status === "failed" ? (
                    <p className="tour-say__note">{m.error || "I could not answer that. Please ask again."}</p>
                  ) : (
                    <>
                      {live.messageId === m.id && live.says.length > 0 && <Answer says={live.says} />}
                      {live.messageId === m.id && live.notices.map((n) => <p key={n} className="tour-say__note">{n}</p>)}
                      <p className="tour__working" role="status">
                        <span className="tour-dots" aria-hidden="true"><i /><i /><i /></span>
                        {words || "Waiting for the guide…"}
                      </p>
                    </>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
        {error && <p className="tour__error" role="alert">{error}</p>}
        <form className="tour-composer" onSubmit={onSubmit}>
          <label className="sr-only" htmlFor={inputId}>Your question</label>
          <input
            id={inputId}
            className="tour-composer__input"
            value={question}
            maxLength={MAX_TOUR_QUESTION_CHARS}
            placeholder={working ? "The guide is working…" : "Ask how something was built…"}
            onChange={(e) => setQuestion(e.target.value)}
            disabled={busy || working}
            autoComplete="off"
          />
          <button type="submit" className="tour-composer__send" disabled={busy || working || !question.trim()} aria-label="Send">
            <ArrowIcon size={16} />
          </button>
        </form>
      </section>

      <div className="tour__side">
        <TourBrowser shot={live.shot} siteUrl={siteUrl} working={working} hasLive={!!siteUrl} />
      </div>
    </div>
  );
}
