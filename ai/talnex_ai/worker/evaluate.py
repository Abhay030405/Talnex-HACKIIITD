"""Check TalNex against a planted app whose right answers we know (AGENTS.md section 9).

    python -m talnex_ai.worker.evaluate --expected eval/expected/honest.json --runs 3

It runs the whole live-testing pipeline several times on the app (a Python worker must be running), then compares
the verdicts with the expected ones and writes the saved runs to eval/runs/<app>/ and a report to eval/report/<app>.md.

The rules it checks (architecture section 27):
  * correctness: each claim gets the expected verdict ("could not test" is reported separately, it is never a wrong answer)
  * steadiness: the same verdict for each claim in at least 2 of 3 runs, and the TalNex score moves by at most 10 points
  * no red flags that should not be there
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from talnex_ai import settings as settings_module
from talnex_ai.claims.store import save_claims
from talnex_ai.db import open_pool
from talnex_ai.db.jobs import start_pipeline
from talnex_ai.formats import Claim
from talnex_ai.worker.live_check import create_subject, stage_states

REPO_ROOT = Path(__file__).resolve().parents[3]


@dataclass
class ClaimRun:
    verdict: Optional[str]            # works / partly_works / broken / could_not_test, or None when there is no result
    confidence: Optional[str] = None
    feature_score: Optional[float] = None
    reason: str = ""


@dataclass
class RunData:
    index: int
    subject_id: str = ""
    finished: bool = True             # every stage reached the end
    seconds: float = 0.0
    cost_usd: float = 0.0
    talnex: Optional[float] = None    # 0 to 100, as stored
    coverage: Optional[float] = None
    flags: list[str] = field(default_factory=list)
    claims: dict[str, ClaimRun] = field(default_factory=dict)


# ------------------------------------------------------------------------------------------ the analysis (pure)


def _required_agreement(runs: int, wanted: int) -> int:
    return min(wanted, runs)


def analyse(expected: dict[str, Any], runs: list[RunData]) -> dict[str, Any]:
    """Compare runs with the expected answers. Pure: no network, no database."""
    criteria = expected.get("criteria", {})
    need = _required_agreement(len(runs), int(criteria.get("verdict_agreement_runs", 2)))
    max_spread = float(criteria.get("talnex_score_spread_max", 10))
    wanted: dict[str, str] = {c["text"]: c["expected"] for c in expected["claims"] + expected.get("controls", [])}
    control_texts = {c["text"] for c in expected.get("controls", [])}

    claims_out = []
    correct = wrong = unconfirmed = 0
    for text, want in wanted.items():
        verdicts = [r.claims[text].verdict if text in r.claims else None for r in runs]
        counted = Counter(v for v in verdicts if v is not None)
        majority, agree = (counted.most_common(1)[0] if counted else (None, 0))
        for v in verdicts:
            if v == want:
                correct += 1
            elif v in (None, "could_not_test"):
                unconfirmed += 1
            else:
                wrong += 1
        scores = [r.claims[text].feature_score for r in runs if text in r.claims and r.claims[text].feature_score is not None]
        claims_out.append({
            "claim": text, "control": text in control_texts, "expected": want, "verdicts": verdicts,
            "majority": majority, "agreeing_runs": agree, "steady": agree >= need,
            "majority_is_expected": majority == want,
            "feature_scores": scores, "score_spread": round(max(scores) - min(scores), 1) if len(scores) > 1 else 0.0,
        })

    talnex = [r.talnex for r in runs if r.talnex is not None]
    spread = round(max(talnex) - min(talnex), 1) if len(talnex) > 1 else 0.0
    flags_per_run = [len(r.flags) for r in runs]
    expected_flags = int(expected.get("expected_flags", 0))
    total = correct + wrong + unconfirmed

    checks = {
        "every run finished": all(r.finished for r in runs),
        "no wrong verdicts": wrong == 0,
        "every claim steady (same verdict in %d of %d runs)" % (need, len(runs)): all(c["steady"] for c in claims_out),
        "majority verdict is the expected one for every claim": all(c["majority_is_expected"] for c in claims_out),
        "TalNex score spread within %g points" % max_spread: spread <= max_spread,
        "no unexpected red flags": all(n == expected_flags for n in flags_per_run),
    }
    return {
        "app": expected["app"], "runs": len(runs), "claims": claims_out,
        "pairs": {"correct": correct, "wrong": wrong, "unconfirmed": unconfirmed, "total": total},
        "accuracy": round(100.0 * correct / total, 1) if total else 0.0,
        "talnex_scores": talnex, "talnex_spread": spread, "flags_per_run": flags_per_run,
        "seconds_per_run": [round(r.seconds) for r in runs], "cost_per_run": [round(r.cost_usd, 4) for r in runs],
        "checks": checks, "passed": all(checks.values()),
    }


def render_report(a: dict[str, Any], when: str, note: str = "") -> str:
    lines = [f"# Evaluation: {a['app']}", "", f"Run on {when}. {a['runs']} runs.{(' ' + note) if note else ''}", "",
             f"**Result: {'PASS' if a['passed'] else 'FAIL'}**", "", "## Checks", ""]
    for name, ok in a["checks"].items():
        lines.append(f"- {'PASS' if ok else 'FAIL'}: {name}")
    p = a["pairs"]
    lines += ["", "## Numbers", "",
              f"- Verdicts matching the expected answer: {p['correct']} of {p['total']} ({a['accuracy']}%)",
              f"- Wrong verdicts: {p['wrong']}",
              f"- Could not test / no result (never a wrong answer): {p['unconfirmed']}",
              f"- TalNex score per run (out of 100): {a['talnex_scores']} (spread {a['talnex_spread']})",
              f"- Red flags per run: {a['flags_per_run']}",
              f"- Seconds per run: {a['seconds_per_run']}",
              f"- Cost per run (US dollars): {a['cost_per_run']}",
              "", "## Claims", "", "| Claim | Expected | Verdicts per run | Steady | Feature scores |", "|---|---|---|---|---|"]
    for c in a["claims"]:
        label = c["claim"][:70] + ("…" if len(c["claim"]) > 70 else "") + (" (control)" if c["control"] else "")
        lines.append(f"| {label} | {c['expected']} | {', '.join(str(v) for v in c['verdicts'])} | "
                     f"{'yes' if c['steady'] else 'NO'} | {c['feature_scores']} |")
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------------------------------ running it for real


def collect(pool, subject, expected: dict[str, Any], index: int, seconds: float, finished: bool) -> RunData:
    column = "project_id" if subject.kind == "project" else "candidate_project_id"
    data = RunData(index=index, subject_id=subject.id, finished=finished, seconds=seconds)
    with pool.connection() as conn:
        for text, verdict, confidence, score, reason in conn.execute(
            f"""SELECT c.text, r.verdict, r.confidence, r.feature_score, r.score_reason
                  FROM claims c LEFT JOIN results r ON r.claim_id = c.id WHERE c.{column} = %s::uuid""", (subject.id,)).fetchall():
            data.claims[text] = ClaimRun(verdict, confidence, float(score) if score is not None else None, reason or "")
        row = conn.execute(f"SELECT score, coverage FROM scores WHERE {column} = %s::uuid AND score_group = 'talnex'", (subject.id,)).fetchone()
        if row:
            data.talnex = float(row[0]) if row[0] is not None else None
            data.coverage = float(row[1])
        data.flags = [f"{r[0]}: {r[1]}" for r in conn.execute(f"SELECT level, reason FROM flags WHERE {column} = %s::uuid", (subject.id,)).fetchall()]
        data.cost_usd = float(conn.execute(
            "SELECT coalesce(sum(u.cost_usd), 0) FROM usage_log u JOIN jobs j ON j.id = u.job_id WHERE j.target_id = %s::uuid",
            (subject.id,)).fetchone()[0])
    return data


def run_once(pool, expected: dict[str, Any], index: int, project: bool, timeout: int) -> RunData:
    subject = create_subject(pool, project=project, url=expected["url"], name=f"Evaluation {expected['app']} #{index}",
                             role=expected.get("role_level", "fresher"))
    save_claims(pool, subject, [
        Claim(text=c["text"], claim_group=c.get("group", "Core"), importance=c.get("importance", 2), source="readme")
        for c in expected["claims"] + expected.get("controls", [])])
    start_pipeline(pool, "live_check_project" if project else "live_check", subject.kind, subject.id)
    started = time.monotonic()
    finished = False
    while time.monotonic() - started < timeout:
        states = stage_states(pool, subject)
        if states.get("feature_score") in ("done", "failed") or "failed" in states.values():
            finished = states.get("feature_score") == "done"
            break
        time.sleep(3)
    return collect(pool, subject, expected, index, time.monotonic() - started, finished)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--expected", required=True, help="the expected-answers file, for example eval/expected/honest.json")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--project", action="store_true", help="test as a hackathon project instead of a resume project")
    parser.add_argument("--timeout", type=int, default=1500, help="seconds to wait for each run")
    parser.add_argument("--note", default="", help="a line added to the report (for example what was different about this run)")
    args = parser.parse_args(argv)

    expected_path = Path(args.expected)
    expected = json.loads((expected_path if expected_path.is_absolute() else REPO_ROOT / expected_path).read_text(encoding="utf-8"))
    pool = open_pool(settings_module.load().database_url)

    runs: list[RunData] = []
    for i in range(1, args.runs + 1):
        print(f"run {i} of {args.runs} ...", flush=True)
        data = run_once(pool, expected, i, args.project, args.timeout)
        runs.append(data)
        shown = ", ".join(f"{(c.verdict or 'none')}" for c in data.claims.values())
        print(f"  finished={data.finished} {data.seconds:.0f}s ${data.cost_usd:.4f} talnex={data.talnex} verdicts: {shown}", flush=True)

    analysis = analyse(expected, runs)
    when = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    runs_dir = REPO_ROOT / "eval" / "runs" / expected["app"]
    runs_dir.mkdir(parents=True, exist_ok=True)
    (runs_dir / f"{stamp}.json").write_text(
        json.dumps({"when": when, "runs": [asdict(r) for r in runs], "analysis": analysis}, indent=2), encoding="utf-8")
    report_dir = REPO_ROOT / "eval" / "report"
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / f"{expected['app']}.md").write_text(render_report(analysis, when, args.note), encoding="utf-8")

    print(f"\n{'PASS' if analysis['passed'] else 'FAIL'}: accuracy {analysis['accuracy']}%, wrong {analysis['pairs']['wrong']}, "
          f"unconfirmed {analysis['pairs']['unconfirmed']}, talnex spread {analysis['talnex_spread']}")
    for name, ok in analysis["checks"].items():
        print(f"  {'PASS' if ok else 'FAIL'}: {name}")
    print(f"report: eval/report/{expected['app']}.md")
    return 0 if analysis["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
