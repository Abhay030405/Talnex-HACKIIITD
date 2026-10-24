"""The interview kit: up to five questions for the recruiter to ask, each tied to the proof behind it.

Plain code over the finished report, no model: the same report always gives the same questions. Questions are neutral
("walk me through"), never accusations, because every point is a thing to talk about, not a verdict. The order follows
how much a point should change the interview: strong coding signals, features that broke, review-worthy flags, features
that partly work, repeated medium paste signals, then features that could not be tested (ask for a live demo).
One medium coding signal alone is never raised (architecture section 18).
"""
from __future__ import annotations

from typing import Any, Iterator, Mapping

MAX_QUESTIONS = 5
MAX_SAME_KIND = 3          # so one long list (five broken features) cannot crowd out everything else
PASTE_SIGNAL = "leetcode_paste"


def _sentence(text: str, limit: int = 300) -> str:
    """What the test saw, as one clean run of text without a closing full stop. Long text is cut at a word."""
    text = " ".join(str(text or "").split()).rstrip(". ")
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0].rstrip(",;:") + "…"
    return text


def _first_seen(feature: Mapping[str, Any]) -> str:
    for step in reversed(feature.get("proof") or []):
        if step.get("observed"):
            return _sentence(step["observed"])
    return _sentence(feature.get("reason") or "")


def _claim(feature: Mapping[str, Any]) -> str:
    return str(feature.get("text") or "").strip().rstrip(".")


def _features(report: Mapping[str, Any], verdicts: tuple[str, ...]) -> Iterator[tuple[Mapping, Mapping]]:
    for project in report.get("projects") or []:
        for feature in project.get("features") or []:
            if feature.get("verdict") in verdicts:
                yield project, feature


def _paste_question(signal: Mapping[str, Any]) -> dict[str, Any]:
    ev = signal.get("evidence") or {}
    where = f"{signal.get('contest') or 'a contest'}, {ev.get('problem') or signal.get('problem') or 'one problem'}"
    return {"kind": "coding", "question": f"In {where}, how did you arrive at your solution? Talk us through it from the "
                                          "first idea to the final code.",
            "why": f"The contest replay shows {ev.get('lines', 'several')} lines added in one go at {ev.get('at', '?')} "
                   f"({ev.get('reason', 'a paste')}). Many people write elsewhere and paste, so this is a question, not a verdict.",
            "proof": {"contest": signal.get("contest"), "at": ev.get("at"), "ranking_url": ev.get("ranking_url")}}


def build_kit(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The interview questions for one candidate report, most important first."""
    out: list[dict[str, Any]] = []
    signals = report.get("coding_signals") or []

    for s in signals:
        if s.get("weight") == "strong":
            out.append(_paste_question(s) if s.get("signal") == PASTE_SIGNAL else {
                "kind": "coding", "question": f"Tell us about your {s.get('site', 'coding')} contest results. "
                                              "How do you usually prepare and work during a contest?",
                "why": f"A strong {str(s.get('signal', '')).replace('_', ' ')} signal. A hint to look at, not proof.",
                "proof": {"contest": s.get("contest")}})

    for project, f in _features(report, ("broken",)):
        out.append({"kind": "feature", "question": f"Your resume says \"{_claim(f)}\" for {project.get('name')}. Our test found: "
                                                   f"{_first_seen(f) or 'it did not work'}. Walk us through how you built it "
                                                   "and what could cause that.",
                    "why": "TalNex tested this feature on the live site and it did not work.",
                    "proof": {"project": project.get("name"), "claim_id": f.get("claim_id")}})

    for flag in report.get("flags") or []:
        if flag.get("level") in ("review", "strong"):
            out.append({"kind": "flag", "question": f"We noticed this about your work: {flag.get('reason')} Can you tell us "
                                                    "how that came about?",
                        "why": f"A {flag.get('level')} flag. It sits beside the score and is never subtracted from it.",
                        "proof": {"flag": flag.get("type")}})

    for project, f in _features(report, ("partly_works",)):
        out.append({"kind": "feature", "question": f"\"{_claim(f)}\" in {project.get('name')} only partly worked in our test: "
                                                   f"{_first_seen(f) or 'some parts did not'}. What is finished, and what would "
                                                   "you do next?",
                    "why": "TalNex found part of this feature working and part not.",
                    "proof": {"project": project.get("name"), "claim_id": f.get("claim_id")}})

    pastes = [s for s in signals if s.get("signal") == PASTE_SIGNAL and s.get("weight") == "medium"]
    if len(pastes) >= 2:
        out.append(_paste_question(pastes[0]))

    role = report.get("role") or {}
    for s in role.get("skills") or []:
        if not s.get("proven_by"):
            out.append({"kind": "skill", "question": f"This role needs {s['skill']}. Tell us about something you built "
                                                     f"with {s['skill']}: what was hard, and how you solved it.",
                        "why": f"None of the features TalNex tested showed {s['skill']}. That is not proof they lack it, "
                               "only that the resume projects did not show it.",
                        "proof": {"skill": s["skill"]}})

    for project, f in _features(report, ("could_not_test",)):
        if f.get("testable"):
            out.append({"kind": "demo", "question": f"Could you show us \"{_claim(f)}\" in {project.get('name')} live?",
                        "why": "TalNex could not test this one. That never counts against the candidate, so a short demo "
                               "settles it.",
                        "proof": {"project": project.get("name"), "claim_id": f.get("claim_id")}})

    kit, per_kind = [], {}
    for q in out:
        if per_kind.get(q["kind"], 0) < MAX_SAME_KIND:
            per_kind[q["kind"]] = per_kind.get(q["kind"], 0) + 1
            kit.append(q)
    return kit[:MAX_QUESTIONS]
