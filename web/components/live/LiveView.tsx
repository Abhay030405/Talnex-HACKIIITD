"use client";

import { useEffect, useReducer, useState } from "react";

import {
  claimWord,
  clock,
  emptyLiveState,
  EVENT_KINDS,
  formatUsd,
  reduceLive,
  tally,
  type Box,
  type LiveEvent,
  type LiveKind,
  type LiveState,
  type LiveSubject,
} from "@/lib/live";

type Action = { type: "event"; kind: string; event: LiveEvent } | { type: "reset" };

function reducer(state: LiveState, action: Action): LiveState {
  return action.type === "reset" ? emptyLiveState() : reduceLive(state, action.kind, action.event);
}

/**
 * What TalNex is doing right now, one panel per project, from the website's own stream route. Every piece of text
 * in the stream comes from the outside world and is shown as plain text only.
 */
export function LiveView({ kind, id, names }: { kind: LiveKind; id: string; names: Record<string, string> }) {
  const [state, dispatch] = useReducer(reducer, undefined, emptyLiveState);
  const [connection, setConnection] = useState<"connecting" | "live" | "reconnecting">("connecting");
  const [focus, setFocus] = useState<string | null>(null);

  useEffect(() => {
    const source = new EventSource(`/api/live/${encodeURIComponent(kind)}/${encodeURIComponent(id)}`);
    source.onopen = () => setConnection("live");
    source.onerror = () => setConnection("reconnecting");
    // A reconnect replays the saved events, so the view starts again from a clean slate.
    source.addEventListener("replay.start", () => dispatch({ type: "reset" }));
    source.addEventListener("replay.done", () => setConnection("live"));
    for (const eventKind of EVENT_KINDS) {
      source.addEventListener(eventKind, (message) => {
        try {
          dispatch({ type: "event", kind: eventKind, event: JSON.parse((message as MessageEvent).data) as LiveEvent });
        } catch {
          // A message that is not JSON is skipped; the stream goes on.
        }
      });
    }
    return () => source.close();
  }, [kind, id]);

  const name = (s: LiveSubject) => names[s.id] ?? `${s.kind.replaceAll("_", " ")} ${s.id.slice(0, 8)}`;
  const subjects = state.order.map((sid) => state.subjects[sid]).filter(Boolean);
  // The whole event's own steps (comparison, AI opinion) go after the teams.
  subjects.sort((a, b) => Number(a.kind === "event") - Number(b.kind === "event"));
  const focused = focus ? state.subjects[focus] : undefined;

  return (
    <div className="live stack">
      <div className="live__meter" role="status">
        <span className={`live__connection live__connection--${connection}`}>{connection}</span>
        <span className="live__stat">
          projects <strong>{subjects.filter((s) => s.kind !== "event").length}</strong>
        </span>
        <span className="live__stat">
          actions <strong>{state.actions}</strong>
        </span>
        <span className="live__stat">
          browser cost <strong>{formatUsd(state.costUsd)}</strong>
        </span>
        <span className="live__stat">
          verdicts <strong>{state.verdicts}</strong>
        </span>
      </div>

      {focused ? (
        <div className="stack">
          <button type="button" className="button button--ghost button--sm live__back" onClick={() => setFocus(null)}>
            ← All projects
          </button>
          <SubjectPanel subject={focused} name={name(focused)} focused />
        </div>
      ) : subjects.length === 0 ? (
        <div className="panel">
          <div className="panel__empty">
            <p>Waiting for a check to start. Each project gets its own panel here as soon as TalNex starts on it.</p>
          </div>
        </div>
      ) : (
        <div className="live__grid">
          {subjects.map((s) => (
            <SubjectPanel key={s.id} subject={s} name={name(s)} onOpen={() => setFocus(s.id)} />
          ))}
        </div>
      )}
    </div>
  );
}

function SubjectPanel({
  subject: s,
  name,
  focused = false,
  onOpen,
}: {
  subject: LiveSubject;
  name: string;
  focused?: boolean;
  onOpen?: () => void;
}) {
  const t = tally(s);
  const log = focused ? s.log : s.log.slice(-60);
  return (
    <section className={focused ? "live-panel live-panel--focus" : "live-panel"} aria-label={name}>
      <div className="live-panel__head">
        {onOpen ? (
          <button type="button" className="live-panel__name live-panel__open" onClick={onOpen}>
            {name}
          </button>
        ) : (
          <h2 className="live-panel__name">{name}</h2>
        )}
        <span className={s.current ? "live-panel__stage live-panel__stage--running" : "live-panel__stage"}>
          {s.current || (s.stages.length ? "waiting" : "")}
        </span>
      </div>

      <div className="live-panel__counts">
        <span>claims {t.total}</span>
        <span className="live-count--works">works {t.works}</span>
        <span className="live-count--broken">broken {t.broken}</span>
        <span className="live-count--other">other {t.other}</span>
        <span>testing {t.testing}</span>
        <span>actions {s.actions}</span>
      </div>

      {s.stages.length > 0 && (
        <ul className="live-stages">
          {s.stages.map(([stage, state]) => (
            <li key={stage} className={`live-stage live-stage--${state}`}>
              {stage}
            </li>
          ))}
        </ul>
      )}

      <div className={focused ? "live-panel__body live-panel__body--focus" : "live-panel__body"}>
        <div className="live-panel__screen">
          <Shot shot={s.shot} />
          {s.label && <p className="live-panel__label">{s.label}</p>}
          {s.reason && <p className="live-panel__reason">“{s.reason}”</p>}
          {focused && s.url && <p className="live-panel__url">{s.url}</p>}
        </div>

        <ul className="live-claims">
          {s.claimOrder.length === 0 && <li className="live-claim">No claims yet.</li>}
          {s.claimOrder.map((cid) => {
            const c = s.claims[cid];
            return (
              <li key={cid} className={`live-claim live-claim--${c.status}`}>
                <span className="live-claim__text">{c.text || "A claim"}</span>
                <span className="live-claim__status">
                  {claimWord(c.status)}
                  {c.confidence ? ` · ${c.confidence}` : ""}
                </span>
                {focused && c.reason && <span className="live-claim__reason">{c.reason}</span>}
              </li>
            );
          })}
        </ul>

        <ol className={focused ? "live-log live-log--focus" : "live-log"} reversed>
          {log
            .slice()
            .reverse()
            .map((line, i) => (
              <li key={`${line.at}-${i}`} className={`live-log__line live-log__line--${line.tone}`}>
                <span className="live-log__at">{clock(line.at)}</span>
                <span className="live-log__label">{line.label}</span>
                <span className="live-log__text">{line.text}</span>
              </li>
            ))}
        </ol>
      </div>
    </section>
  );
}

/** The agent's latest screen. The ring marks where it last clicked, drawn over the picture in its own pixels. */
function Shot({ shot }: { shot: { url: string; box?: Box } | null }) {
  const [size, setSize] = useState<{ url: string; w: number; h: number } | null>(null);
  if (!shot) return <div className="live-shot live-shot--empty">No screen yet</div>;
  const box = shot.box;
  const known = size && size.url === shot.url ? size : null;
  return (
    <div className="live-shot">
      {/* A short-lived signed link from the API; plain img, so no image domain needs to be configured. */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        className="live-shot__img"
        src={shot.url}
        alt="The agent's screen"
        onLoad={(e) => setSize({ url: shot.url, w: e.currentTarget.naturalWidth, h: e.currentTarget.naturalHeight })}
      />
      {known && box && (
        <svg className="live-shot__overlay" viewBox={`0 0 ${known.w} ${known.h}`} preserveAspectRatio="none" aria-hidden>
          <circle
            className="live-shot__ring"
            cx={box.x + box.w / 2}
            cy={box.y + box.h / 2}
            r={Math.max(14, known.w / 60)}
          />
        </svg>
      )}
    </div>
  );
}
