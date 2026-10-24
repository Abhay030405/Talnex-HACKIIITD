"""Reading the cloned code for each claim, the "missing" safeguard, the stage, track reconciling, and the score stage's evidence."""
import json
import re
import uuid
from types import SimpleNamespace

import pytest

from talnex_ai.claims.store import Subject, load_claims, save_claims
from talnex_ai.db.jobs import Job
from talnex_ai.formats import Claim, Result
from talnex_ai.llm.structured import StructuredError
from talnex_ai.sandbox.client import ExecResult, SandboxError
from talnex_ai.sandbox.code_review import choose_files, claim_words, evidence_text, review_claim
from talnex_ai.sandbox.route_discovery import Discovery, Route, to_json
from talnex_ai.sandbox.store import code_review_for_claim, create_run, save_code_review, update_run
from talnex_ai.scoring.store import save_result
from talnex_ai.settings import SandboxSettings
from talnex_ai.testing.runner import store
from talnex_ai.worker.handlers import code_review as stage_module
from talnex_ai.worker.handlers import feature_score as score_module
from talnex_ai.worker.handlers import track_reconcile as reconcile_module
from talnex_ai.worker.registry import JobContext
from talnex_ai.worker.services import Services, set_services

CODE = {
    "app/main.py": "from rag import answer\n@app.post('/ask')\ndef ask(q):\n    return answer(q)\n",
    "app/rag.py": "def answer(q):\n    docs = retrieve(q)\n    if not relevant(docs, q):\n        q = rewrite(q)\n        docs = retrieve(q)\n    return llm(q, docs)\n",
    "app/models.py": "class User: pass\n",
    "app/utils.py": "def helper(): pass\n",
    "README.md": "# app\n",
}


class FakeVm:
    """A VM holding CODE: answers the file list, a grep for a word, and the read script."""

    def __init__(self, files=None, gone=False):
        self.files, self.gone, self.commands = files or CODE, gone, []

    def exec(self, command, **kw):
        if self.gone:
            raise SandboxError("that VM no longer exists")
        self.commands.append(command)
        if "git ls-files" in command:
            return ExecResult(0, stdout="\n".join(self.files))
        m = re.search(r"grep -rIli --include='\*' -e '?(\w+)'? ", command)
        if m:
            word = m.group(1).lower()
            return ExecResult(0, stdout="\n".join(f for f, t in self.files.items() if word in t.lower()))
        paths = re.findall(r'@@@TALNEX-FILE ([^"]+)"', command)
        return ExecResult(0, stdout="\n".join(f"@@@TALNEX-FILE {p}\n{self.files.get(p, '')}\n" for p in paths))


class Model:
    def __init__(self, *replies):
        self.replies, self.calls = list(replies), []

    def chat(self, role, messages, **kw):
        self.calls.append((role, messages[1]["content"]))
        text = self.replies.pop(0)
        return SimpleNamespace(text=text if isinstance(text, str) else json.dumps(text))


def finding(mechanism="present", summary="It retries with a rewritten question."):
    return {"mechanism": mechanism, "summary": summary,
            "evidence": [{"file": "app/rag.py", "line": 3, "what": "checks the documents are relevant"}, {"file": "app/rag.py", "line": 4, "what": "rewrites the question"}],
            "quality": [{"good": False, "point": "no timeout on the model call", "file": "app/rag.py", "line": 6}],
            "ai": {"is_ai_feature": True, "model_call": True, "error_handling": False, "output_validated": None, "keys_from_environment": True}}


FILES = list(CODE)


class TestChoosingFiles:
    def test_words_of_a_claim(self):
        assert claim_words("Self-corrective RAG that rewrites the question when documents are not relevant")[:2] == ["corrective", "document"] or "rewrite" in claim_words("Self-corrective RAG that rewrites the question when documents are not relevant")
        assert claim_words("Upload an image and get a caption") == ["caption", "upload", "image"]

    def test_files_that_mention_the_words_rank_first_and_a_small_app_is_fully_shown(self):
        chosen = choose_files(FakeVm(), "rewrites the question when documents are not relevant", FILES, "app", max_files=2)
        assert chosen.paths[0] == "app/rag.py" and len(chosen.paths) == 2 and chosen.all_source_shown is False
        assert choose_files(FakeVm(), "rewrite the question", FILES, "app", max_files=12).all_source_shown is True

    def test_a_route_file_the_claim_is_linked_to_is_lifted(self):
        chosen = choose_files(FakeVm(), "something unrelated entirely", FILES, "app", linked_files=["main.py"], max_files=1)
        assert chosen.paths == ["app/main.py"]

    def test_no_source_files_gives_nothing_to_read(self):
        assert choose_files(FakeVm({"README.md": "x"}), "anything", ["README.md"], "").paths == []


class TestReviewClaim:
    def test_a_finding_comes_back_with_the_files_that_were_read(self):
        model = Model(finding())
        out, chosen = review_claim(model, FakeVm(), "rewrites the question when documents are not relevant", FILES, "app")
        assert out.mechanism == "present" and out.evidence[0].line == 3 and out.ai.is_ai_feature and "app/rag.py" in chosen.paths
        prompt = model.calls[0][1]
        assert "   3|     if not relevant(docs, q):" in prompt and "all_source_files_shown: true" in prompt

    def test_missing_is_only_believed_when_enough_code_was_read(self):
        many = {**CODE, **{f"app/extra{i}.py": "x = 1\n" for i in range(20)}}
        # 22 source files, 2 read, none of the claim's words found in them: "missing" becomes "unclear"
        out, _ = review_claim(Model(finding("missing")), FakeVm(many), "zebra quokka feature", list(many), "app", max_files=2)
        assert out.mechanism == "unclear" and "Not enough of the code was read" in out.summary
        # the whole app was shown: "missing" stands
        out, chosen = review_claim(Model(finding("missing")), FakeVm(), "zebra quokka feature", FILES, "app", max_files=12)
        assert chosen.all_source_shown and out.mechanism == "missing"

    def test_no_source_means_unclear_and_no_model_call(self):
        model = Model()
        out, _ = review_claim(model, FakeVm({"README.md": "x"}), "anything", ["README.md"], "")
        assert out.mechanism == "unclear" and model.calls == []

    def test_the_evidence_text_is_labelled_and_says_what_was_found(self):
        f = {**finding("partial"), "all_source_shown": True}
        text = evidence_text(f)
        assert text.startswith("Code review (read from the code, not run): the claimed mechanism is only partly there.")
        assert "evidence: app/rag.py:3" in text and "weak: no timeout on the model call" in text and "errors handled: no" in text
        assert "was NOT found" in evidence_text({"mechanism": "missing", "all_source_shown": False}) and "Only some of the code was read" in evidence_text({"mechanism": "missing", "all_source_shown": False})


# ------------------------------------------------------------------ the stage


@pytest.fixture
def project(pool):
    with pool.connection() as conn:
        uid = conn.execute("INSERT INTO users (email) VALUES (%s) RETURNING id", (f"{uuid.uuid4()}@t.example",)).fetchone()[0]
        eid = conn.execute("INSERT INTO events (owner_id, name, mode, starts_at, ends_at) VALUES (%s, 'E', 'open_theme', now(), now() + interval '1 day') RETURNING id",
                           (uid,)).fetchone()[0]
        return conn.execute("INSERT INTO projects (event_id, team_name, repo_url) VALUES (%s, 'T', 'https://github.com/a/b') RETURNING id::text", (eid,)).fetchone()[0]


class Client:
    def __init__(self, vm):
        self.vm = vm

    def attach(self, vm_id):
        return self.vm


def start_run(pool, project, discovery=None):
    run_id = create_run(pool, Subject("project", project))
    update_run(pool, run_id, status="running", resources={"vm_id": "vm1", "port": 3000, "app_dir": "app", "discovery": to_json(discovery or Discovery())})
    return run_id


def run_stage(pool, project, vm, model):
    cfg = SimpleNamespace(sandbox=SandboxSettings("http://x", "t", 900, 600, 20, review_max_files=12, review_max_kb=120))
    set_services(Services(cfg, pool, model, None, None, lambda host: None, None, sandbox=Client(vm)))
    job = Job(str(uuid.uuid4()), "code_review", "python", "project", project, {}, "sandbox_check_project", 1, 1, 3, 3000)
    try:
        return stage_module.code_review(job, JobContext(job, pool))
    finally:
        set_services(None)


def verdict_of(pool, claim_id):
    with pool.connection() as conn:
        return conn.execute("SELECT verdict, confidence, reason FROM results WHERE claim_id = %s::uuid", (claim_id,)).fetchone()


class TestCodeReviewStage:
    def claims(self, pool, project):
        return save_claims(pool, Subject("project", project), [
            Claim(text="Self-corrective retrieval that rewrites the question", claim_group="Core", importance=3, source="criteria"),
            Claim(text="Users get a caption for a photo", claim_group="Core", importance=2, source="criteria"),
            Claim(text="Shows a leaderboard of top scores", claim_group="Core", importance=1, source="criteria"),
            Claim(text="The route GET /health exists and responds sensibly", claim_group="Core", importance=1, source="route", track="sandbox"),
            Claim(text="POST /ask answers bad input without crashing", claim_group="Edge cases", importance=2, source="route", track="sandbox"),
        ])

    def test_findings_are_kept_with_the_run_and_untested_claims_get_reviewed_from_code(self, pool, project):
        rag, caption, board, route, edge = self.claims(pool, project)
        start_run(pool, project)
        model = Model(finding("present"), finding("missing", "There is no captioning code."), {"mechanism": "unclear", "summary": "cannot tell"})
        out = run_stage(pool, project, FakeVm(), model)
        assert out["reviewed"] == 3 and out["mechanisms"] == {"present": 1, "missing": 1, "unclear": 1} and len(model.calls) == 3
        # the claims TalNex made up from the routes are not reviewed
        assert verdict_of(pool, route.id) is None and verdict_of(pool, edge.id) is None
        v, conf, reason = verdict_of(pool, rag.id)
        assert v == "reviewed_from_code" and conf == "medium" and reason.startswith("reviewed from code, not run")
        v, _, reason = verdict_of(pool, caption.id)
        assert v == "reviewed_from_code" and "not found in the code" in reason
        assert verdict_of(pool, board.id) is None                      # unclear says nothing and lowers nothing
        assert code_review_for_claim(pool, rag.id)["mechanism"] == "present" and code_review_for_claim(pool, rag.id)["files_read"]

    def test_a_claim_that_was_really_tested_keeps_its_verdict_and_gets_the_review_as_evidence(self, pool, project):
        rag, caption, board, *_ = self.claims(pool, project)
        save_result(pool, Result(claim_id=rag.id, verdict="works", confidence="high", reason="the live test passed"))
        save_result(pool, Result(claim_id=caption.id, verdict="could_not_test", confidence="low", reason="not tested: no live link was given"))
        start_run(pool, project)
        run_stage(pool, project, FakeVm(), Model(finding("present"), finding("partial"), {"mechanism": "unclear", "summary": "x"}))
        assert verdict_of(pool, rag.id)[0] == "works"
        assert verdict_of(pool, caption.id)[0] == "reviewed_from_code"      # a could-not-test is replaced by what the code shows
        assert code_review_for_claim(pool, rag.id) is not None

    def test_nothing_running_or_a_vm_that_ended_is_skipped_and_one_bad_answer_does_not_stop_the_rest(self, pool, project):
        self.claims(pool, project)
        assert run_stage(pool, project, FakeVm(), Model())["skipped"]
        start_run(pool, project)
        assert run_stage(pool, project, FakeVm(gone=True), Model())["skipped"]
        out = run_stage(pool, project, FakeVm(), Model("nope", "nope", finding("present"), {"mechanism": "unclear"}))
        assert out["reviewed"] >= 1


# ------------------------------------------------------------------ both tracks must agree


class TestTrackReconcile:
    def test_the_state_of_a_track_from_its_runs(self):
        s = reconcile_module.track_state
        assert s(["passed"]) == "good" and s(["failed", "passed"]) == "good" and s(["failed", "failed"]) == "bad"
        assert s(["failed"]) == "unknown" and s(["blocked", "blocked"]) == "unknown" and s([]) == "unknown"

    def test_what_counts_as_a_contradiction(self):
        r = reconcile_module.reconcile
        assert r("works", "good", "bad")[0] and r("partly_works", "bad", "good")[0] and r("broken", "good", "bad")[0]
        assert not r("works", "good", "good")[0] and not r("works", "good", "unknown")[0] and not r("broken", "bad", "bad")[0]
        assert not r("could_not_test", "good", "bad")[0]

    def test_a_disagreement_becomes_could_not_test_with_the_reason(self, pool, project):
        (c,) = save_claims(pool, Subject("project", project), [Claim(text="Add an item", claim_group="Core", importance=2, source="criteria", track="both")])
        save_result(pool, Result(claim_id=c.id, verdict="works", confidence="high", reason="the live test passed"))
        live = store.create_run(pool, c.id, 1, "normal", track="live")
        store.finish_run(pool, live, "passed")
        for n in (2, 3):
            run = store.create_run(pool, c.id, n, "normal", track="sandbox", method="http")
            store.finish_run(pool, run, "failed")
        job = Job(str(uuid.uuid4()), "track_reconcile", "python", "project", project, {}, "hackathon", 1, 1, 3, 600)
        out = reconcile_module.track_reconcile(job, JobContext(job, pool))
        assert out == {"checked": 1, "disagreed": 1}
        verdict, confidence, reason = verdict_of(pool, c.id)
        assert (verdict, confidence) == ("could_not_test", "disagree") and "live site" in reason and "repository tests" in reason

    def test_a_repository_run_with_a_failed_step_is_not_counted_as_agreeing_with_a_failed_live_site(self, pool, project):
        # Seen on the planted ShelfMate app: the export route answered 500 in the sandbox, but the run is saved as "passed" (its
        # sign-up and sign-in steps passed), so the live failure was reported as "not confirmed" instead of staying broken.
        from talnex_ai.formats import StepRecord
        (c,) = save_claims(pool, Subject("project", project), [Claim(text="Export the shelf", claim_group="Core", importance=2, source="readme", track="both")])
        save_result(pool, Result(claim_id=c.id, verdict="broken", confidence="high", reason="the live site failed twice"))
        for n in (1, 2):
            store.finish_run(pool, store.create_run(pool, c.id, n, "normal", track="live"), "failed")
        sandbox = store.create_run(pool, c.id, 3, "normal", track="sandbox", method="http")
        store.add_steps(pool, sandbox, [StepRecord(step_number=1, kind="http", action="POST /api/signup", observed="pass: status 201"),
                                        StepRecord(step_number=2, kind="http", action="GET /api/books/export", observed="fail: status 500")])
        store.finish_run(pool, sandbox, "passed")
        job = Job(str(uuid.uuid4()), "track_reconcile", "python", "project", project, {}, "hackathon", 1, 1, 3, 600)
        assert reconcile_module.track_reconcile(job, JobContext(job, pool)) == {"checked": 1, "disagreed": 0}
        assert verdict_of(pool, c.id)[0] == "broken"

    def test_no_claim_on_both_tracks_is_skipped(self, pool, project):
        save_claims(pool, Subject("project", project), [Claim(text="Add an item", claim_group="Core", importance=2, source="criteria")])
        job = Job(str(uuid.uuid4()), "track_reconcile", "python", "project", project, {}, "hackathon", 1, 1, 3, 600)
        assert reconcile_module.track_reconcile(job, JobContext(job, pool))["skipped"]


# ------------------------------------------------------------------ the score stage sees the evidence


class TestScoreEvidence:
    def test_a_derived_claim_uses_its_own_run_as_the_main_test_and_the_code_review_is_added(self, pool, project):
        (c,) = save_claims(pool, Subject("project", project), [Claim(text="POST /ask answers bad input without crashing", claim_group="Edge cases",
                                                                    importance=2, source="route", track="sandbox")])
        save_result(pool, Result(claim_id=c.id, verdict="partly_works", confidence="medium", reason="2 of 9 steps failed"))
        run_id = store.create_run(pool, c.id, 1, "edge_case", track="sandbox", method="http")
        from talnex_ai.formats import StepRecord
        store.add_steps(pool, run_id, [StepRecord(step_number=1, kind="http", action="POST /ask (an empty JSON body)", observed="fail: status 500; expected an answer below 500")])
        store.finish_run(pool, run_id, "passed")
        sub_run = start_run(pool, project)
        save_code_review(pool, sub_run, c.id, {"mechanism": "partial", "summary": "Input is not validated.", "evidence": [], "quality": [], "ai": {}, "all_source_shown": True})
        verdict, confidence, reason, evidence = score_module.evidence_text(pool, c.id)
        assert verdict == "partly_works" and "Steps of the main test run" in evidence and "status 500" in evidence
        assert "Extra check" not in evidence                         # its own run is the main one, not an "extra"
        assert "Code review (read from the code, not run)" in evidence and "Input is not validated." in evidence
