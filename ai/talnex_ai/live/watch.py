"""Watch live events in a terminal: a debugging tool, and a live view before the website page exists.

    python -m talnex_ai.live.watch                 # everything
    python -m talnex_ai.live.watch --subject <id>  # one project or candidate
"""
from __future__ import annotations

import argparse
import json
import sys

import psycopg

from talnex_ai import settings as settings_module
from talnex_ai.live.events import CHANNEL


def describe(event: dict) -> str:
    """One readable line per event."""
    data = event.get("data") or {}
    kind = event.get("kind", "?")
    where = " · ".join(str(event[k]) for k in ("stage",) if event.get(k))
    text = {
        "stage.started": lambda: f"stage {event.get('stage')} started",
        "stage.finished": lambda: f"stage {event.get('stage')} finished in {data.get('seconds')}s"
                                  + (f" (skipped: {data.get('reason')})" if data.get("skipped") else ""),
        "stage.failed": lambda: f"stage {event.get('stage')} failed, now {data.get('status')}: {data.get('error')}",
        "claim.started": lambda: f"testing claim: {data.get('text')}",
        "run.started": lambda: f"browser run {data.get('try_number')} started ({data.get('test_type')})",
        "reason": lambda: f"  reason: {data.get('text')}",
        "step.record": lambda: f"  {data.get('label')}" + (f"  [{data.get('proof_key')}]" if data.get("proof_key") else ""),
        "step.result": lambda: f"  step {data.get('step')} {data.get('result')}: {data.get('observed')}",
        "run.outcome": lambda: f"run says {data.get('outcome')}: {data.get('observed')}",
        "run.finished": lambda: f"browser run ended: {data.get('outcome')}, {data.get('actions')} actions, ${data.get('cost_usd')}",
        "ladder": lambda: f"ladder: {data.get('line')}",
        "check": lambda: f"blind check: {data.get('outcome')} ({data.get('seen')})",
        "verdict": lambda: f"VERDICT {data.get('verdict')} ({data.get('confidence')}): {data.get('reason')}",
    }.get(kind, lambda: f"{kind} {json.dumps(data)}")()
    stamp = (event.get("at") or "")[11:19]
    return f"{stamp}  {where:<14} {text}"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--subject", help="only events about this project, candidate or event id")
    args = parser.parse_args(argv)
    url = settings_module.load().database_url
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute(f"LISTEN {CHANNEL}")
        print(f"listening on '{CHANNEL}' (Ctrl+C to stop)")
        try:
            for note in conn.notifies():
                event = json.loads(note.payload)
                if args.subject and event.get("subject", {}).get("id") != args.subject:
                    continue
                print(describe(event), flush=True)
        except KeyboardInterrupt:
            return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
