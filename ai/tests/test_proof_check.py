import json
import uuid
from dataclasses import dataclass

import pytest

from talnex_ai.db import jobs as queue
from talnex_ai.formats import Result
from talnex_ai.llm.structured import StructuredError
from talnex_ai.scoring.store import save_result
from talnex_ai.testing.proof_check import check_proof
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


def test_only_the_last_screenshots_are_looked_at_and_the_verdict_is_never_shown():
    model = FakeChecker({"outcome": "works", "seen": "Four egg recipes are listed.", "screenshot_clear": True})
    files = Files()
    result = check(model, files, ["s/1", None, "s/2", "s/3", "s/4", "s/5"])
    assert (result.outcome, result.images_used) == ("works", 4)
    assert files.read == ["s/2", "s/3", "s/4", "s/5"]
    role, messages, options = model.calls[0]
    assert role == "proof_checker" and options["temperature"] == 0.0
    prompt = messages[1]["content"][0]["text"]
    assert "egg recipes are listed" in prompt and "4 screenshots" in prompt and "agent" not in prompt.lower()


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
