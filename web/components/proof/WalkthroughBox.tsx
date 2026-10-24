"use client";

import { useCallback, useEffect, useId, useRef, useState, type FormEvent } from "react";

import type { ProofRef, Walkthrough, WalkthroughAnswer, WalkthroughSubject } from "@/lib/types";
import {
  DEFAULT_LABEL,
  MAX_QUESTION_CHARS,
  POLL_EVERY_MS,
  POLL_GIVE_UP_MS,
  choiceQuestion,
  isFinished,
  missingStatusWords,
  pickRecordingType,
  refInfo,
  walkthroughStatusWords,
} from "@/lib/walkthrough-format";

async function readJson<T>(response: Response): Promise<T & { error?: string }> {
  try {
    return (await response.json()) as T & { error?: string };
  } catch {
    return { error: response.ok ? undefined : "Something went wrong. Please try again." } as T & { error?: string };
  }
}

const canSpeak = () => typeof window !== "undefined" && "speechSynthesis" in window;

/** Ask in words or by voice how a feature works; the answer points to its proof. An explanation, never a score. */
export function WalkthroughBox({ subject, subjectId }: { subject: WalkthroughSubject; subjectId: string }) {
  const inputId = useId();
  const [question, setQuestion] = useState("");
  const [history, setHistory] = useState<Walkthrough[]>([]);
  const [current, setCurrent] = useState<Walkthrough | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [recording, setRecording] = useState(false);
  const recorder = useRef<MediaRecorder | null>(null);
  const polling = useRef(0);

  const loadHistory = useCallback(async () => {
    const query = new URLSearchParams({ subject, id: subjectId });
    const response = await fetch(`/api/walkthroughs?${query}`, { cache: "no-store" });
    if (response.ok) setHistory((await response.json()) as Walkthrough[]);
  }, [subject, subjectId]);

  useEffect(() => {
    void loadHistory();
    return () => {
      polling.current++;
      if (canSpeak()) window.speechSynthesis.cancel();
      recorder.current?.stream.getTracks().forEach((t) => t.stop());
    };
  }, [loadHistory]);

  /** Asks every so often whether the answer is ready; stops when it is, or after a few minutes. */
  const follow = useCallback(
    async (id: string) => {
      const ticket = ++polling.current;
      const until = Date.now() + POLL_GIVE_UP_MS;
      while (ticket === polling.current && Date.now() < until) {
        await new Promise((r) => setTimeout(r, POLL_EVERY_MS));
        if (ticket !== polling.current) return;
        const response = await fetch(`/api/walkthroughs/${encodeURIComponent(id)}`, { cache: "no-store" });
        const data = await readJson<Walkthrough>(response);
        if (!response.ok) {
          setError(data.error ?? "Could not get the answer.");
          return;
        }
        setCurrent(data);
        if (isFinished(data.status)) {
          void loadHistory();
          return;
        }
      }
      if (ticket === polling.current)
        setError("The answer is taking longer than usual. It will appear under earlier questions.");
    },
    [loadHistory],
  );

  async function send(body: FormData) {
    setBusy(true);
    setError(null);
    body.set("subject", subject);
    body.set("id", subjectId);
    try {
      const response = await fetch("/api/walkthroughs", { method: "POST", body });
      const data = await readJson<{ id: string; status: Walkthrough["status"] }>(response);
      if (!response.ok || !data.id) {
        setError(data.error ?? "The question could not be sent.");
        return;
      }
      setCurrent({
        id: data.id,
        status: data.status,
        question: String(body.get("question") ?? "") || null,
        answer: null,
        error: null,
        created_at: new Date().toISOString(),
        answered_at: null,
      });
      setQuestion("");
      void follow(data.id);
    } catch {
      setError("Cannot reach the website. Check your connection and try again.");
    } finally {
      setBusy(false);
    }
  }

  function ask(text: string) {
    const clean = text.trim();
    if (!clean) return setError("Type a question first.");
    const body = new FormData();
    body.set("question", clean.slice(0, MAX_QUESTION_CHARS));
    void send(body);
  }

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    ask(question);
  }

  async function startRecording() {
    setError(null);
    const type = pickRecordingType(
      typeof MediaRecorder === "undefined" ? undefined : (t) => MediaRecorder.isTypeSupported(t),
    );
    if (!type || !navigator.mediaDevices?.getUserMedia) {
      return setError("This browser cannot record. Type the question instead.");
    }
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      return setError("The microphone was not allowed. Type the question instead.");
    }
    const parts: Blob[] = [];
    const active = new MediaRecorder(stream, { mimeType: type });
    active.ondataavailable = (e) => e.data.size > 0 && parts.push(e.data);
    active.onstop = () => {
      stream.getTracks().forEach((t) => t.stop());
      setRecording(false);
      const audio = new Blob(parts, { type });
      if (audio.size === 0) return setError("Nothing was recorded. Try again.");
      const body = new FormData();
      body.set("audio", audio, `question.${type.split("/")[1]}`);
      void send(body);
    };
    recorder.current = active;
    active.start();
    setRecording(true);
  }

  function speak(text: string) {
    if (!canSpeak() || !text) return;
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(new SpeechSynthesisUtterance(text));
  }

  return (
    <section className="walkthrough" aria-labelledby={`${inputId}-title`}>
      <h3 className="walkthrough__title" id={`${inputId}-title`}>
        Ask about this project
      </h3>
      <p className="note">
        Ask how a feature works. The answer comes from the code and the test results, with links to the proof. It is an
        explanation, not a score.
      </p>

      <form className="walkthrough__form" onSubmit={onSubmit}>
        <label className="sr-only" htmlFor={inputId}>
          Your question
        </label>
        <input
          className="input"
          id={inputId}
          value={question}
          maxLength={MAX_QUESTION_CHARS}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="How does the login work?"
          disabled={busy || recording}
        />
        <div className="row">
          <button type="submit" className="button button--soft" disabled={busy || recording}>
            {busy ? "Sending…" : "Ask"}
          </button>
          <button
            type="button"
            className="button button--ghost"
            onClick={() => (recording ? recorder.current?.stop() : void startRecording())}
            disabled={busy}
            aria-pressed={recording}
          >
            {recording ? "Stop and send" : "Ask by voice"}
          </button>
          {recording && (
            <span className="walkthrough__recording" role="status">
              Recording… speak your question, then press stop.
            </span>
          )}
        </div>
      </form>

      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}

      {current && (
        <div className="walkthrough__answer" aria-live="polite">
          <p className="walkthrough__question">{current.question || "Spoken question"}</p>
          {!isFinished(current.status) && <p className="note">{walkthroughStatusWords(current.status)}</p>}
          {current.status === "failed" && (
            <p className="form-error">{current.error || "This question could not be answered."}</p>
          )}
          {current.answer && (
            <AnswerView answer={current.answer} onChoose={(text) => ask(choiceQuestion(text))} onSpeak={speak} />
          )}
        </div>
      )}

      {history.length > 0 && (
        <details className="walkthrough__history">
          <summary>Earlier questions ({history.length})</summary>
          <ul className="plain-list stack stack--tight">
            {history.map((w) => (
              <li key={w.id}>
                <button
                  type="button"
                  className="walkthrough__earlier"
                  onClick={() => {
                    polling.current++;
                    setCurrent(w);
                    if (!isFinished(w.status)) void follow(w.id);
                  }}
                >
                  {w.question || "Spoken question"} · {walkthroughStatusWords(w.status)}
                </button>
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}

function Refs({ refs }: { refs: ProofRef[] }) {
  if (refs.length === 0) return null;
  return (
    <span className="walkthrough__refs">
      {refs.map((ref, i) => {
        const info = refInfo(ref);
        return info.url ? (
          <a key={i} className="walkthrough__ref" href={info.url} target="_blank" rel="noopener noreferrer">
            {info.label}
          </a>
        ) : (
          <span key={i} className="walkthrough__ref" title={info.note}>
            {info.label}
          </span>
        );
      })}
    </span>
  );
}

function AnswerView({
  answer,
  onChoose,
  onSpeak,
}: {
  answer: WalkthroughAnswer;
  onChoose: (text: string) => void;
  onSpeak: (text: string) => void;
}) {
  return (
    <div className="stack stack--tight">
      <div className="row">
        <span className="badge badge--neutral">{answer.label || DEFAULT_LABEL}</span>
        {answer.spoken && canSpeak() && (
          <button type="button" className="button button--ghost button--sm" onClick={() => onSpeak(answer.spoken)}>
            Read aloud
          </button>
        )}
      </div>
      {answer.claim_text && <p className="walkthrough__claim">About: {answer.claim_text}</p>}
      {answer.not_found && <p className="note">That could not be found in the code or the test results.</p>}

      {answer.choices.length > 0 && !answer.claim_id && (
        <div className="stack stack--tight">
          <p className="note">Which feature do you mean?</p>
          <div className="row">
            {answer.choices.map((c) => (
              <button
                key={c.claim_id}
                type="button"
                className="button button--ghost button--sm"
                onClick={() => onChoose(c.text)}
              >
                {c.text}
              </button>
            ))}
          </div>
        </div>
      )}

      {answer.flow.length > 0 && (
        <>
          <h4 className="walkthrough__heading">How it works</h4>
          <ol className="walkthrough__list">
            {answer.flow.map((s, i) => (
              <li key={i}>
                {s.text} <Refs refs={s.proof} />
              </li>
            ))}
          </ol>
        </>
      )}

      {answer.seen.length > 0 && (
        <>
          <h4 className="walkthrough__heading">What TalNex saw</h4>
          <ul className="walkthrough__list">
            {answer.seen.map((s, i) => (
              <li key={i}>
                {s.text} <Refs refs={s.proof} />
              </li>
            ))}
          </ul>
        </>
      )}

      {answer.missing.length > 0 && (
        <>
          <h4 className="walkthrough__heading">What is missing</h4>
          <ul className="walkthrough__list">
            {answer.missing.map((m, i) => (
              <li key={i}>
                {m.item}: {missingStatusWords(m.status)} <Refs refs={m.proof} />
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
