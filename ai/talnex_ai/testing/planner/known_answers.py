"""Known-answer tests (architecture section 14): inputs where we already know the correct answer.

The planner is shown the entries that fit a claim and builds the Logic test from one of them.
Files named here live in the test files folder (TEST_FILES_DIR, default testdata).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from talnex_ai.formats import Claim


@dataclass(frozen=True)
class KnownAnswer:
    key: str
    # Patterns (regular expressions, matched as whole words at the start) for claims this entry fits.
    # They name the FEATURE, not common words: "add a todo" is not a calculator.
    matches: tuple[str, ...]
    kind: str        # what sort of feature it tests
    use_input: str   # what to give the feature
    expect: str      # what a correct answer looks like
    asset: str = ""  # a file to upload, if the input is a file


LIBRARY: tuple[KnownAnswer, ...] = (
    KnownAnswer(
        key="image_caption",
        matches=(r"caption", r"describ\w* (?:an? |the |your )?(?:image|photo|picture)", r"image recogni",
                 r"object detect", r"what(?:'s| is) in (?:an? |the |your )?(?:image|photo|picture)", r"alt text"),
        kind="image captioner",
        use_input="a clear photo of a single dog",
        expect="the caption or description mentions a dog",
        asset="known_answers/dog.jpg",
    ),
    KnownAnswer(
        key="resume_skills",
        matches=(r"r[eé]sum[eé]", r"\bcv\b", r"skills? (?:extract|pars|match)"),
        kind="resume analyzer",
        use_input="the TalNex test resume, which lists Python, Docker and PostgreSQL",
        expect="the analysis finds Python, Docker and PostgreSQL as skills",
        asset="known_answers/test_resume.pdf",
    ),
    KnownAnswer(
        key="currency_convert",
        matches=(r"currenc", r"exchange rate", r"forex", r"convert\w* (?:\w+ )?(?:money|usd|inr|eur|dollars?|rupees?)"),
        kind="currency converter",
        use_input="100 USD converted to INR",
        expect="a result in a sensible range, roughly 7,000 to 11,000 INR",
    ),
    KnownAnswer(
        key="summarize",
        matches=(r"summar", r"tl;?dr", r"key points"),
        kind="summarizer",
        use_input="this short text: 'The Eiffel Tower is in Paris. It was finished in 1889 and is about 330 metres tall.'",
        expect="the summary mentions the Eiffel Tower and Paris",
    ),
    KnownAnswer(
        key="arithmetic",
        matches=(r"calculat", r"arithmetic", r"math (?:solver|problems?|expressions?)", r"solve equations?"),
        kind="calculator",
        use_input="12 plus 30",
        expect="the answer is 42",
    ),
    KnownAnswer(
        key="translate",
        matches=(r"translat",),
        kind="translator",
        use_input="the English sentence 'Good morning' translated to Spanish",
        expect="the result is 'Buenos días' or very close to it",
    ),
)

_PATTERNS = {entry.key: re.compile("|".join(rf"\b(?:{p})" for p in entry.matches), re.IGNORECASE)
             for entry in LIBRARY}


def matching_entries(claim: Claim) -> list[KnownAnswer]:
    """The library entries that fit a claim, judged by what its text says the feature does."""
    return [entry for entry in LIBRARY if _PATTERNS[entry.key].search(claim.text)]
