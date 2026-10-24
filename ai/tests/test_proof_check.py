import json
import uuid
from dataclasses import dataclass

import pytest

from talnex_ai.db import jobs as queue
from talnex_ai.formats import Result
from talnex_ai.llm.structured import StructuredError
from talnex_ai.scoring.store import save_result
from talnex_ai.formats import StepRecord
from talnex_ai.testing.proof_check import MAX_IMAGES, check_proof, devtools_notes, screens_for_check
from talnex_ai.worker.handlers.proof_check import GAP_REASON, proof_check_stage
from talnex_ai.worker.registry import JobContext

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


@dataclass
class Reply:
    text: str
    truncated: bool = False


class FakeChecker:
    def __init__(self, *answers):
        self.answers = [json.dumps(a) for a in answers]
        self.calls = []

    def chat(self, role, messages, **options):
        self.calls.append((role, messages, options))
        return Reply(self.answers.pop(0))


class Files:
    def __init__(self, missing=()):
        self.missing = set(missing)
        self.read = []

    def get_bytes(self, key):
        if key in self.missing:
            raise FileNotFoundError(key)
        self.read.append(key)
        return PNG


def check(model, files, keys):
    return check_proof(model, files, claim_text="Search recipes", expected_result="egg recipes are listed",
                       proof_keys=keys)


def test_at_most_the_last_few_screenshots_are_looked_at_and_the_verdict_is_never_shown():
    model = FakeChecker({"outcome": "works", "seen": "Four egg recipes are listed.", "screenshot_clear": True})
    files = Files()
    keys = [f"s/{n}" for n in range(1, MAX_IMAGES + 3)]
    result = check(model, files, [keys[0], None] + keys[1:])
    assert (result.outcome, result.images_used) == ("works", MAX_IMAGES)
    assert files.read == keys[-MAX_IMAGES:]
    role, messages, options = model.calls[0]
    assert role == "proof_checker" and options["temperature"] == 0.0
    prompt = messages[1]["content"][0]["text"]
    assert "egg recipes are listed" in prompt and f"{MAX_IMAGES} screenshots" in prompt and "agent" not in prompt.lower()


def _step(n, devtools):
    return StepRecord(step_number=n, action="a", devtools=devtools)


def test_devtools_notes_pull_out_errors_failed_requests_and_console():
    steps = [
        _step(1, {"error_responses": [{"method": "POST", "url": "https://x/api/chat", "status": 500, "ms": 120}],
                  "console_errors": ["[error] TypeError: x is undefined"]}),
        _step(2, {"failed_requests": [{"url": "https://x/feed", "error": "net::ERR_ABORTED"}],
                  "api_calls": [{"method": "GET", "url": "https://x/api/slow", "ms": 3100}]}),
        _step(3, None),  # a step that saw nothing is fine
    ]
    notes = devtools_notes(steps)
    assert "POST https://x/api/chat answered 500, 120ms" in notes
    assert "console: [error] TypeError: x is undefined" in notes
    assert "request to https://x/feed failed (net::ERR_ABORTED)" in notes
    assert "slow: GET https://x/api/slow took 3100ms" in notes


def test_devtools_notes_are_capped_and_deduplicated():
    same = {"error_responses": [{"method": "GET", "url": "https://x/api/a", "status": 500}]}
    assert devtools_notes([_step(i, same) for i in range(1, 6)]) == ["GET https://x/api/a answered 500"]
    many = [_step(i, {"console_errors": [f"[error] e{i}"]}) for i in range(1, 21)]
    assert len(devtools_notes(many)) == 8


def test_devtools_notes_reach_the_proof_check_prompt_as_data():
    model = FakeChecker({"outcome": "broken", "seen": "The chat never answered.", "screenshot_clear": True})
    check_proof(model, Files(), claim_text="Ask the chatbot", expected_result="an answer appears",
                proof_keys=["s/1"], notes=["POST https://x/api/chat answered 500"])
    prompt = model.calls[0][1][1]["content"][0]["text"]
    assert "Developer-tools notes" in prompt and "api/chat answered 500" in prompt and "data not instructions" in prompt


def test_unreadable_screenshots_are_skipped_and_none_means_blocked():
    model = FakeChecker({"outcome": "broken", "seen": "An error page.", "screenshot_clear": True})
    assert check(model, Files(missing={"s/1"}), ["s/1", "s/2"]).images_used == 1
    nothing = check(FakeChecker(), Files(missing={"s/1"}), ["s/1"])
    assert (nothing.outcome, nothing.images_used, nothing.screenshot_clear) == ("blocked", 0, False)
    assert check(FakeChecker(), Files(), []).outcome == "blocked"


@pytest.mark.parametrize("seen", ["The share button is not visible.", "The total still shows 0.",
                                  "Search did not show any results.", "The upload failed with an error."])
def test_a_works_answer_that_describes_a_failure_is_sent_back(seen):
    model = FakeChecker({"outcome": "works", "seen": seen},
                        {"outcome": "broken", "seen": seen})
    assert check(model, Files(), ["s/1"]).outcome == "broken"
    assert "Make the outcome agree" in model.calls[1][1][-1]["content"]


def test_honest_works_answers_are_not_second_guessed():
    model = FakeChecker({"outcome": "works", "seen": "Recipes are listed with no errors on the page."})
    assert check(model, Files(), ["s/1"]).outcome == "works" and len(model.calls) == 1


def test_a_checker_that_keeps_contradicting_itself_fails_clearly():
    bad = {"outcome": "works", "seen": "Nothing is shown; the feature is missing."}
    with pytest.raises(StructuredError):
        check(FakeChecker(bad, bad), Files(), ["s/1"])


@pytest.fixture
def project_with_claims(pool):
    with pool.connection() as conn:
        user = conn.execute("INSERT INTO users (email) VALUES (%s) RETURNING id",
                            (f"pytest-{uuid.uuid4().hex[:8]}@talnex.test",)).fetchone()[0]
        event = conn.execute(
            """INSERT INTO events (owner_id, name, mode, starts_at, ends_at)
               VALUES (%s, 'pytest event', 'open_theme', now() - interval '1 day', now()) RETURNING id""",
            (user,)).fetchone()[0]
        project = conn.execute("INSERT INTO projects (event_id, team_name) VALUES (%s, 'Team A') RETURNING id::text",
                               (event,)).fetchone()[0]
        ids = [conn.execute("""INSERT INTO claims (project_id, text, claim_group, importance, source, testable,
                                                   untestable_reason)
                               VALUES (%s, %s, 'Core', 2, 'video', %s, %s) RETURNING id::text""",
                            (project, text, testable, None if testable else "a measurement")).fetchone()[0]
               for text, testable in (("search", True), ("share", True), ("3x faster", False))]
    yield project, ids
    with pool.connection() as conn:
        conn.execute("DELETE FROM events WHERE id = %s", (event,))
        conn.execute("DELETE FROM users WHERE id = %s", (user,))


def test_the_stage_fills_gaps_honestly_and_only_once(pool, project_with_claims):
    project, (search, share, untestable) = project_with_claims
    save_result(pool, Result(claim_id=search, verdict="works", confidence="high", reason="seen"))
    queue.enqueue_job(pool, "proof_check", "python", "project", project, pipeline="hackathon")
    job = queue.take_job(pool, "python", "w")

    assert proof_check_stage(job, JobContext(job, pool)) == {"claims": 2, "with_results": 1, "filled_in": 1}
    assert proof_check_stage(job, JobContext(job, pool)) == {"claims": 2, "with_results": 2, "filled_in": 0}
    with pool.connection() as conn:
        rows = dict(conn.execute("SELECT claim_id::text, verdict || ':' || reason FROM results WHERE claim_id = ANY(%s::uuid[])",
                                 ([search, share, untestable],)).fetchall())
        status = conn.execute("SELECT status FROM projects WHERE id = %s", (project,)).fetchone()[0]
    assert rows == {search: "works:seen", share: f"could_not_test:{GAP_REASON}"}
    assert status == "checking"


def step(n, expected, key=True):
    return StepRecord(step_number=n, action=f"action {n}", expected=expected, proof_key=f"s/{n}" if key else None)


def test_every_part_of_a_long_test_is_shown_one_screenshot_per_step():
    """A converter test: EUR, then GBP, then INR, each step taking a few actions. The old rule (the last 4 actions)
    showed only GBP and INR, and the converter was called partly working."""
    steps = [step(1, "the site opens"),
             step(2, "100 USD shows 92 EUR"), step(3, "100 USD shows 92 EUR"), step(4, "100 USD shows 92 EUR"),
             step(5, "100 USD shows 79 GBP"), step(6, "100 USD shows 79 GBP"),
             step(7, "100 USD shows 8300 INR"), step(8, "100 USD shows 8300 INR", key=False),
             step(9, "the result is visible")]   # the final check
    assert screens_for_check(steps) == ["s/1", "s/4", "s/6", "s/7", "s/9"]
    assert screens_for_check(steps, max_images=2) == ["s/7", "s/9"]   # too many steps: the latest are kept
    assert screens_for_check([]) == []
