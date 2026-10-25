"""Check TalNex against a planted app whose right answers we know (AGENTS.md section 9).

    python -m talnex_ai.worker.evaluate --expected eval/expected/honest.json --runs 3
    python -m talnex_ai.worker.evaluate --all --runs 1      (every planted app side by side: the gate before a merge)

It runs the whole live-testing pipeline several times on the app (a Python worker must be running), then compares
the verdicts with the expected ones and writes the saved runs to eval/runs/<app>/ and a report to eval/report/<app>.md.

The rules it checks (architecture section 27):
  * correctness: each claim gets the expected verdict ("could not test" is reported separately, it is never a wrong answer).
    An expected verdict can be a list when more than one answer is right, for example ["broken", "partly_works"]
  * steadiness: the same verdict for each claim in at least 2 of 3 runs, and the TalNex score moves by at most 10 points
  * no red flags that should not be there
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from concurrent.futures import ThreadPoolExecutor
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
from talnex_ai.worker.sandbox_check import create_subject as create_repo_subject

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


def _right(verdict: Optional[str], want: Any) -> bool:
    """Whether a verdict is one of the expected answers (one verdict, or a list of acceptable ones)."""
    return verdict in want if isinstance(want, list) else verdict == want


def _label(want: Any) -> str:
    return " or ".join(want) if isinstance(want, list) else str(want)


def analyse(expected: dict[str, Any], runs: list[RunData]) -> dict[str, Any]:
    """Compare runs with the expected answers. Pure: no network, no database."""
    criteria = expected.get("criteria", {})
    need = _required_agreement(len(runs), int(criteria.get("verdict_agreement_runs", 2)))
    max_spread = float(criteria.get("talnex_score_spread_max", 10))
    wanted: dict[str, Any] = {c["text"]: c["expected"] for c in expected["claims"] + expected.get("controls", [])}
    control_texts = {c["text"] for c in expected.get("controls", [])}

    claims_out = []
    correct = wrong = unconfirmed = 0
    for text, want in wanted.items():
        verdicts = [r.claims[text].verdict if text in r.claims else None for r in runs]
        counted = Counter(v for v in verdicts if v is not None)
        majority, agree = (counted.most_common(1)[0] if counted else (None, 0))
        claim_wrong = 0
        for v in verdicts:
            if _right(v, want):
                correct += 1
            elif v in (None, "could_not_test"):
                unconfirmed += 1
            else:
                wrong += 1
                claim_wrong += 1
        scores = [r.claims[text].feature_score for r in runs if text in r.claims and r.claims[text].feature_score is not None]
        claims_out.append({
            "claim": text, "control": text in control_texts, "expected": _label(want), "verdicts": verdicts,
            "majority": majority, "agreeing_runs": agree, "steady": agree >= need,
            "majority_is_expected": _right(majority, want), "wrong_runs": claim_wrong,
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


def run_once_repo(pool, expected: dict[str, Any], index: int, project: bool, timeout: int) -> RunData:
    """A repo-only app (no live link): the sandbox track clones the repo into a throwaway VM and tests its routes."""
    subject = create_repo_subject(pool, repo=expected["repo"], name=f"Evaluation {expected['app']} #{index}", candidate=not project)
    save_claims(pool, subject, [
        Claim(text=c["text"], claim_group=c.get("group", "Core"), importance=c.get("importance", 2), source="readme", track="sandbox")
        for c in expected["claims"] + expected.get("controls", [])])
    start_pipeline(pool, "sandbox_check_project" if project else "sandbox_check", subject.kind, subject.id)
    started = time.monotonic()
    finished = False
    while time.monotonic() - started < timeout:
        states = stage_states(pool, subject)
        if states.get("sandbox_end") in ("done", "failed") or "failed" in states.values():
            finished = states.get("sandbox_end") == "done"
            break
        time.sleep(3)
    return collect(pool, subject, expected, index, time.monotonic() - started, finished)


def run_once(pool, expected: dict[str, Any], index: int, project: bool, timeout: int) -> RunData:
    if expected.get("repo") and not expected.get("url"):
        return run_once_repo(pool, expected, index, project, timeout)
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
    parser.add_argument("--expected", help="the expected-answers file, for example eval/expected/honest.json")
    parser.add_argument("--all", action="store_true", help="every file in eval/expected that tests a live site or a repo, side by side")
    parser.add_argument("--dir", help="a folder of expected-answers files, for example eval/expected/login")
    parser.add_argument("--skip", default="", help="with --dir: skip files whose name contains any of these words, comma separated")
    parser.add_argument("--only", default="", help="with --dir: keep only files whose name contains any of these words, comma separated")
    parser.add_argument("--out", default="", help="save reports in eval/report/<this folder> (for example login_before) instead of eval/report")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--project", action="store_true", help="test as a hackathon project instead of a resume project")
    parser.add_argument("--timeout", type=int, default=1500, help="seconds to wait for each run")
    parser.add_argument("--note", default="", help="a line added to the report (for example what was different about this run)")
    args = parser.parse_args(argv)
    if [bool(args.all), bool(args.expected), bool(args.dir)].count(True) != 1:
        parser.error("give one of --expected <file>, --dir <folder> or --all")

    if args.all:
        files = [f for f in sorted((REPO_ROOT / "eval" / "expected").glob("*.json"))
                 if json.loads(f.read_text(encoding="utf-8")).get("url") or json.loads(f.read_text(encoding="utf-8")).get("repo")]
    elif args.dir:
        folder = Path(args.dir) if Path(args.dir).is_absolute() else REPO_ROOT / args.dir
        skip = [w.strip() for w in args.skip.split(",") if w.strip()]
        only = [w.strip() for w in args.only.split(",") if w.strip()]
        files = [f for f in sorted(folder.glob("*.json"))
                 if not any(w in f.name for w in skip) and (not only or any(w in f.name for w in only))]
    else:
        path = Path(args.expected)
        files = [path if path.is_absolute() else REPO_ROOT / path]
    global REPORT_SUBDIR
    REPORT_SUBDIR = args.out
    apps = [json.loads(f.read_text(encoding="utf-8")) for f in files]
    pool = open_pool(settings_module.load().database_url, max_size=4 + len(apps))
    with ThreadPoolExecutor(max_workers=len(apps)) as threads:
        results = list(threads.map(lambda e: evaluate_app(pool, e, args.runs, args.project, args.timeout, args.note), apps))
    if len(results) > 1:
        write_summary(results, args.note)
    return 0 if all(a["passed"] for a in results) else 1


def evaluate_app(pool, expected: dict[str, Any], runs_wanted: int, project: bool, timeout: int, note: str) -> dict[str, Any]:
    """Run one app the asked number of times, save the runs and the report, and return the analysis."""
    app = expected["app"]
    runs: list[RunData] = []
    for i in range(1, runs_wanted + 1):
        print(f"[{app}] run {i} of {runs_wanted} ...", flush=True)
        data = run_once(pool, expected, i, project, timeout)
        runs.append(data)
        shown = ", ".join(f"{(c.verdict or 'none')}" for c in data.claims.values())
        print(f"[{app}]  finished={data.finished} {data.seconds:.0f}s ${data.cost_usd:.4f} talnex={data.talnex} verdicts: {shown}",
              flush=True)

    analysis = analyse(expected, runs)
    when = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    runs_dir = REPO_ROOT / "eval" / "runs" / expected["app"]
    runs_dir.mkdir(parents=True, exist_ok=True)
    (runs_dir / f"{stamp}.json").write_text(
        json.dumps({"when": when, "runs": [asdict(r) for r in runs], "analysis": analysis}, indent=2), encoding="utf-8")
    report_dir = REPO_ROOT / "eval" / "report" / REPORT_SUBDIR
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / f"{expected['app']}.md").write_text(render_report(analysis, when, note), encoding="utf-8")

    print(f"\n[{app}] {'PASS' if analysis['passed'] else 'FAIL'}: accuracy {analysis['accuracy']}%, wrong {analysis['pairs']['wrong']}, "
          f"unconfirmed {analysis['pairs']['unconfirmed']}, talnex spread {analysis['talnex_spread']}")
    for name, ok in analysis["checks"].items():
        print(f"[{app}]   {'PASS' if ok else 'FAIL'}: {name}")
    print(f"[{app}] report: {report_dir.relative_to(REPO_ROOT).as_posix()}/{expected['app']}.md", flush=True)
    return analysis


REPORT_SUBDIR = ""  # set by main from --out


def render_summary(results: list[dict[str, Any]], when: str, note: str = "") -> str:
    """One table for every app: the gate's answer at a glance."""
    passed = all(a["passed"] for a in results)
    lines = ["# Evaluation: every planted app", "", f"Run on {when}.{(' ' + note) if note else ''}", "",
             f"**Gate: {'PASS' if passed else 'FAIL'}**", "",
             "| App | Result | Right | Wrong | Could not test | Seconds per run | Cost per run (USD) |",
             "|---|---|---|---|---|---|---|"]
    for a in results:
        p = a["pairs"]
        lines.append(f"| {a['app']} | {'PASS' if a['passed'] else 'FAIL'} | {p['correct']} of {p['total']} | {p['wrong']} | "
                     f"{p['unconfirmed']} | {a['seconds_per_run']} | {a['cost_per_run']} |")
    wrong = [(a["app"], c) for a in results for c in a["claims"] if c.get("wrong_runs")]
    if wrong:
        lines += ["", "## Wrong verdicts", ""] + [f"- {app}: {c['claim']} (expected {c['expected']}, got {', '.join(str(v) for v in c['verdicts'])})"
                                                for app, c in wrong]
    return "\n".join(lines) + "\n"


def write_summary(results: list[dict[str, Any]], note: str = "") -> None:
    when = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    folder = REPO_ROOT / "eval" / "report" / REPORT_SUBDIR
    folder.mkdir(parents=True, exist_ok=True)
    name = "summary.md" if not REPORT_SUBDIR else f"summary_{results[0]['app'].split('_')[1]}.md"  # one file per batch of apps
    (folder / name).write_text(render_summary(results, when, note), encoding="utf-8")
    print("\n" + render_summary(results, when, note), flush=True)


if __name__ == "__main__":
    sys.exit(main())
