"""Keeping a test to what the claim actually promises.

Two mistakes seen in real runs, both caught here by plain code so a model can't talk its way past them:

1. A plan that checks MORE than the claim. "The About page explains the app" was marked partly working
   because the plan also demanded "private pages stay blocked when signed out", which the claim never said.
2. A count, total or progress claim passed at its starting value. "Set a reading goal with a progress
   bar" was called working at "0 of 12 (0%)", which would show the same if the bar did nothing.
"""
from __future__ import annotations

import re
from typing import Optional

# (what a plan may add on its own, what the claim must say for that to be fair)
_EXTRA_REQUIREMENTS: tuple[tuple[str, re.Pattern, re.Pattern], ...] = (
    ("private pages are blocked",
     re.compile(r"\b(?:signed|logged) out\b|\bprivate (?:pages?|areas?|routes?|content)\b|\bunauthori[sz]ed\b|"
                r"\b(?:stay|stays|are|is|be) (?:blocked|protected|restricted)\b", re.IGNORECASE),
     re.compile(r"private|block|protect|restrict|signed out|logged out|unauthori|permission|only (?:the )?(?:owner|signed|logged)",
                re.IGNORECASE)),
    ("speed",
     re.compile(r"\b(?:within|under|in less than) \d+(?:\.\d+)? ?(?:ms|milliseconds?|s|sec|seconds?)\b|\bload time\b",
                re.IGNORECASE),
     re.compile(r"fast|quick|speed|second|instant|load time|real[- ]time", re.IGNORECASE)),
    ("phone or mobile layout",
     re.compile(r"\bmobile\b|\bphone (?:width|screen|size)\b|\bresponsive\b", re.IGNORECASE),
     re.compile(r"mobile|phone|responsive|tablet|small screen", re.IGNORECASE)),
)

# Claims whose proof is a value that follows other actions.
_FOLLOWS_ACTIONS = re.compile(
    r"\b(?:progress|counts?|counter|how many|totals?|averages?|percent(?:age)?|streaks?|left|remaining|goals?|"
    r"tall(?:y|ies)|stats|statistics|summary of|scores?)\b", re.IGNORECASE)

# A value still at its starting point.
_STARTING_VALUE = re.compile(
    r"(?<![\d.,])0 ?%|(?<![\d.,])0(?:\.0+)? (?:of|out of)\b|\b(?:empty|unfilled) (?:progress )?bar\b|\bbar (?:is |stays )?empty\b|"
    r"\bnone yet\b|\bno (?:books|items|tasks|entries) (?:finished|completed|done)\b", re.IGNORECASE)

# Wording that shows the value was moved by the test ("from 1 item left to 0 items left").
_SHOWS_CHANGE = re.compile(r"\bfrom\b[^.;]{1,40}\bto\b|\bchanged\b|\bwent (?:up|down)\b|\bdropp?ed\b|\brose\b|\bincreased\b|"
                           r"\bdecreased\b|\bafter (?:finishing|completing|marking|adding|ticking|deleting|rating)\b",
                           re.IGNORECASE)


def extra_requirement(claim_text: str, plan_text: str) -> Optional[str]:
    """What a plan checks that the claim never promised, or None."""
    for name, in_plan, in_claim in _EXTRA_REQUIREMENTS:
        if in_plan.search(plan_text) and not in_claim.search(claim_text):
            return name
    return None


def follows_actions(claim_text: str) -> bool:
    """Whether the claim's proof is a value (count, total, progress) that other actions should change."""
    return bool(_FOLLOWS_ACTIONS.search(claim_text))


def unchanged_value(claim_text: str, text: str) -> Optional[str]:
    """For a count, total or progress claim: the starting value that `text` treats as proof, or None.

    "0 of 12 (0%)" proves nothing on its own. "Went from 1 item left to 0 items left" does, so a value
    shown changing is accepted."""
    if not follows_actions(claim_text):
        return None
    found = _STARTING_VALUE.search(text)
    if found and not _SHOWS_CHANGE.search(text):
        return found.group(0)
    return None
