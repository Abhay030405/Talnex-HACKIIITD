"use client";

import Link from "next/link";
import { useEffect, useReducer } from "react";

import { emptyLiveState, EVENT_KINDS, reduceLive, stageWord, type LiveEvent, type LiveState } from "@/lib/live";

type Action = { type: "event"; kind: string; event: LiveEvent } | { type: "reset" };

function reducer(state: LiveState, action: Action): LiveState {
  return action.type === "reset" ? emptyLiveState() : reduceLive(state, action.kind, action.event);
}

/** One candidate on the wall: its own stream, the newest screen of any of its projects, and what runs now. */
function Tile({ id, name }: { id: string; name: string }) {
  const [state, dispatch] = useReducer(reducer, undefined, emptyLiveState);

  useEffect(() => {
    const source = new EventSource(`/api/live/candidate/${encodeURIComponent(id)}`);
    source.addEventListener("replay.start", () => dispatch({ type: "reset" }));
    for (const kind of EVENT_KINDS) {
      source.addEventListener(kind, (message) => {
        try {
          dispatch({ type: "event", kind, event: JSON.parse((message as MessageEvent).data) as LiveEvent });
        } catch {
          // A message that is not JSON is skipped.
        }
      });
    }
    return () => source.close();
  }, [id]);

  const subjects = state.order.map((sid) => state.subjects[sid]).filter(Boolean);
  const active = [...subjects].reverse().find((s) => s.screen || s.shot) ?? subjects[subjects.length - 1];
  const picture = active?.screen ?? active?.shot?.url ?? null;
  const running = subjects.find((s) => s.current);

  return (
    <Link className="live-wall__tile" href={`/candidates/${encodeURIComponent(id)}/live`}>
      <span className="live-wall__name">{name}</span>
      <span className="meta">{running ? stageWord(running.current) : subjects.length ? "Waiting" : "Not started"}</span>
      {picture ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img className="live-wall__img" src={picture} alt={`${name}: the agent's screen`} />
      ) : (
        <div className="live-shot live-shot--empty">No screen yet</div>
      )}
      {active?.label && <span className="meta">{active.label}</span>}
    </Link>
  );
}

/** Every candidate of a role at once, each tile live. Capped so a big batch does not open too many streams. */
export function RoleLiveWall({ candidates }: { candidates: { id: string; name: string }[] }) {
  return (
    <div className="live-wall">
      {candidates.map((c) => (
        <Tile key={c.id} id={c.id} name={c.name} />
      ))}
    </div>
  );
}
