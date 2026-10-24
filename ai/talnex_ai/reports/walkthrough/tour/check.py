"""Plain code that checks the guide's plan against the real code before anything is said (architecture section 32.3).

A sentence is kept only if at least one of its proof references points at lines that exist in the code. A browser step
is kept only if the safety rules allow it. The model's word is never enough."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import quote

from talnex_ai.formats.tour import TourPlan
from talnex_ai.sandbox.code_vm import CodeReadError, CodeVm, clean_path
from talnex_ai.testing.planner.planner import forbidden_action

log = logging.getLogger("talnex.tour")

BLOB = "https://github.com/{repo}/blob/{sha}/{path}#L{start}-L{end}"


@dataclass
class Snippet:
    """Code lines that back a sentence: a verified file and line range, and the lines themselves."""

    file: str
    start: int
    end: int
    commit: Optional[str]
    url: Optional[str]
    lines: list[str]


@dataclass
class CheckedStep:
    say: str
    snippets: list[Snippet]
    show: Optional[str]
    expect: Optional[str]
    notes: list[str] = field(default_factory=list)  # why something was left out, for the log and the page


def check_plan(plan: TourPlan, code: CodeVm, *, repo: Optional[str], commit: Optional[str],
               snippet_lines: int) -> tuple[list[CheckedStep], list[str]]:
    """The steps that survive, and the reasons the rest were dropped."""
    kept: list[CheckedStep] = []
    dropped: list[str] = []
    for number, step in enumerate(plan.steps, start=1):
        snippets: list[Snippet] = []
        for proof in step.proof:
            if proof.kind != "code" or not proof.file or not proof.start:
                continue  # only code proof can be checked here; the guide cannot know screenshots or step ids
            try:
                path = clean_path(proof.file)
                total = code.line_count(path)
            except CodeReadError:
                continue
            if not path or not total or proof.start > total:
                continue
            end = min(max(proof.end or proof.start, proof.start), total)
            shown_end = min(end, proof.start + snippet_lines - 1)
            try:
                lines = code.lines(path, proof.start, shown_end)
            except CodeReadError:
                continue
            link = BLOB.format(repo=repo, sha=commit, path=quote(path), start=proof.start, end=end) if repo and commit else None
            snippets.append(Snippet(path, proof.start, end, commit, link, lines))
        if not snippets:
            dropped.append(f"step {number} has no proof that exists in the code")
            continue
        notes: list[str] = []
        show = step.show
        if show and (risky := forbidden_action(show)):
            notes.append(f'not shown in the browser, because it involves "{risky}"')
            show = None
        kept.append(CheckedStep(step.say, snippets, show, step.expect, notes))
    return kept, dropped
