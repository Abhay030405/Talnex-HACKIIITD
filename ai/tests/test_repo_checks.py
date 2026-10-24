"""Hackathon repository checks: code before the event, one big upload, and sponsor tools really used."""
import uuid

import pytest

from talnex_ai.checks.event_dates import date_flags
from talnex_ai.checks.sponsor_usage import candidate_source_files, decide, find_uses, mentioned
from talnex_ai.db.jobs import Job
from talnex_ai.tinyfish.client import FetchResult
from talnex_ai.worker.handlers import repo_checks as stage_module
from talnex_ai.worker.registry import JobContext
from talnex_ai.worker.services import Services, set_services


# ------------------------------------------------------------------ flags from the dates


def facts(**over):
    return {"found": True, "share_before_start_pct": 10.0, "repo_created_before_start": False, "files": 5, **over}


class TestDateFlags:
    def test_little_old_code_gives_no_flag(self):
        assert date_flags(facts(share_before_start_pct=30.0)) == []

    def test_a_third_of_the_code_is_a_review_flag(self):
        (f,) = date_flags(facts(share_before_start_pct=45.0))
        assert (f.flag_type, f.level) == ("code_before_event", "review") and "45%" in f.reason

    def test_strong_needs_both_over_sixty_percent_and_a_repository_created_before_the_start(self):
        assert date_flags(facts(share_before_start_pct=80.0, repo_created_before_start=True))[0].level == "strong"
        # Commit dates can be faked, so without GitHub's own creation record it stays a review flag.
        assert date_flags(facts(share_before_start_pct=80.0, repo_created_before_start=False))[0].level == "review"
        assert date_flags(facts(share_before_start_pct=60.0, repo_created_before_start=True))[0].level == "review"

    def test_one_big_upload_is_only_information(self):
        (f,) = date_flags(facts(one_big_upload=True))
        assert (f.flag_type, f.level) == ("one_big_upload", "info")

    def test_no_repository_or_an_empty_one_gives_no_flags(self):
        assert date_flags({"found": False, "reason": "no repository link was given"}) == []
        assert date_flags({"found": True, "empty": True}) == []
        assert date_flags({}) == []


# ------------------------------------------------------------------ sponsor tools in the code


class TestSourceFiles:
    def test_only_the_teams_source_files_nearest_the_top_first(self):
        files = ["README.md", "src/deep/very/x.js", "app.js", "tests/app.test.js", "node_modules/a/b.js",
                 "api/pay.py", "vite.config.js", "src/util.spec.ts", "docs/example.py", "logo.png"]
        assert candidate_source_files(files) == ["app.js", "api/pay.py", "src/deep/very/x.js"]

    def test_the_limit_is_respected(self):
        assert len(candidate_source_files([f"f{i}.js" for i in range(100)], limit=10)) == 10


class TestFindUses:
    def test_a_call_counts_but_an_import_or_a_comment_does_not(self):
        text = "import Stripe from 'stripe'\n// stripe is great\nconst s = new Stripe(key)\nawait stripe.charges.create()\n"
        uses = find_uses("Stripe", {"api/pay.js": text})
        assert [(u.file, u.line) for u in uses] == [("api/pay.js", 3), ("api/pay.js", 4)]

    def test_only_an_import_is_not_use(self):
        assert find_uses("Stripe", {"a.js": "import Stripe from 'stripe'\nconst x = require('stripe')\n"}) == []

    def test_a_name_with_spaces_matches_with_or_without_them(self):
        assert find_uses("Google Cloud", {"a.py": "client = google_cloud.storage.Client()\n"})
        assert find_uses("Google Cloud", {"a.py": "client = GoogleCloud()\n"})

    def test_a_name_that_is_too_short_is_never_searched(self):
        assert find_uses("AI", {"a.py": "ai = 1\n"}) == [] and mentioned("AI", "ai ai ai") is False

    def test_readme_mention(self):
        assert mentioned("Twilio", "We send texts with twilio!") and not mentioned("Twilio", "We send texts.")


class TestDecide:
    def d(self, **kw):
        base = dict(listed=False, used=False, in_readme=False, partial=False)
        return decide("Stripe", **{**base, **kw})

    def test_listed_and_used_is_fine(self):
        assert self.d(listed=True, used=True).level is None

    def test_used_without_a_dependency_is_fine_it_may_be_called_over_http(self):
        assert self.d(used=True).level is None

    def test_listed_only_or_readme_only_is_review(self):
        assert self.d(listed=True).level == "review"
        assert self.d(in_readme=True).level == "review"

    def test_neither_is_strong_but_only_review_when_we_could_not_read_all_the_code(self):
        assert self.d().level == "strong"
        assert self.d(partial=True).level == "review"


# ------------------------------------------------------------------ the stage


class FetchFiles:
    """Stands in for TinyFish Fetch: serves the given raw files and says 404 for the rest."""

    def __init__(self, pages):
        self.pages, self.fetched = pages, []

    def fetch(self, urls, **_):
        self.fetched += list(urls)
        return [FetchResult(url=u, ok=True, text=self.pages[u]) if u in self.pages
                else FetchResult(url=u, ok=False, error_code="page_not_found", http_status=404) for u in urls]


def raw(path):
    return f"https://raw.githubusercontent.com/team/app/main/{path}"


@pytest.fixture
def project(pool):
    with pool.connection() as conn:
        uid = conn.execute("INSERT INTO users (email) VALUES (%s) RETURNING id", (f"{uuid.uuid4()}@t.example",)).fetchone()[0]
        eid = conn.execute(
            "INSERT INTO events (owner_id, name, mode, starts_at, ends_at, sponsor_tools) "
            "VALUES (%s, 'E', 'open_theme', now(), now() + interval '1 day', %s) RETURNING id",
            (uid, ["Stripe", "Twilio", "Supabase"])).fetchone()[0]
        return conn.execute("INSERT INTO projects (event_id, team_name, repo_url) VALUES (%s, 'T', 'https://github.com/team/app') RETURNING id::text",
                            (eid,)).fetchone()[0]


def save_stage(pool, project_id, name, result):
    import json
    with pool.connection() as conn:
        conn.execute(
            """INSERT INTO jobs (job_type, runner, target_type, target_id, pipeline, run_number, status, result, dedupe_key)
               VALUES (%s, 'go', 'project', %s::uuid, 'hackathon', 1, 'done', %s::jsonb, %s)""",
            (name, project_id, json.dumps(result), f"{project_id}:{name}"))


def run(pool, project_id, tinyfish):
    set_services(Services(None, pool, None, tinyfish, None, lambda host: None, None))
    job = Job(str(uuid.uuid4()), "repo_checks", "python", "project", project_id, {}, "hackathon", 1, 1, 3, 60)
    try:
        return stage_module.repo_checks(job, JobContext(job, pool))
    finally:
        set_services(None)


def flags(pool, project_id):
    with pool.connection() as conn:
        return sorted(conn.execute("SELECT flag_type, level, reason FROM flags WHERE project_id = %s::uuid", (project_id,)).fetchall())


GITHUB = {"found": True, "repo": "team/app", "default_branch": "main", "files": ["README.md", "app.js", "pay.js"],
          "files_truncated": False}
TOOLS = {"found": True, "tools": [
    {"tool": "Stripe", "listed": True, "matches": [{"file": "package.json", "dependency": "stripe"}]},
    {"tool": "Twilio", "listed": False, "matches": []},
    {"tool": "Supabase", "listed": False, "matches": []}]}


class TestRepoChecksStage:
    def pages(self):
        return {raw("README.md"): "We use Twilio for texts.", raw("app.js"): "console.log('hi')",
                raw("pay.js"): "import Stripe from 'stripe'\nconst s = new Stripe(k)\n"}

    def test_flags_are_raised_beside_the_facts_and_a_used_tool_gets_none(self, pool, project):
        save_stage(pool, project, "github_check", GITHUB)
        save_stage(pool, project, "event_dates", {"found": True, "share_before_start_pct": 85.0,
                                                   "repo_created_before_start": True, "one_big_upload": True})
        save_stage(pool, project, "sponsor_files", TOOLS)
        out = run(pool, project, FetchFiles(self.pages()))

        assert [(t, l) for t, l, _ in flags(pool, project)] == [
            ("code_before_event", "strong"), ("one_big_upload", "info"),
            ("sponsor_tech_not_used", "review"),   # Twilio: only in the README
            ("sponsor_tech_not_used", "strong")]   # Supabase: nowhere
        used = {v["tool"]: v for v in out["sponsors"]}
        assert used["Stripe"]["used"] and used["Stripe"]["flag"] is None
        assert used["Twilio"]["in_readme"] and used["Twilio"]["flag"] == "review"
        assert out["repo_vs_live"]["skipped"] and out["repo_vs_live"]["reason"]   # never "not built yet"

    def test_running_twice_does_not_pile_up_flags(self, pool, project):
        save_stage(pool, project, "github_check", GITHUB)
        save_stage(pool, project, "event_dates", {"found": True, "share_before_start_pct": 85.0, "repo_created_before_start": True})
        save_stage(pool, project, "sponsor_files", TOOLS)
        run(pool, project, FetchFiles(self.pages()))
        first = flags(pool, project)
        run(pool, project, FetchFiles(self.pages()))
        assert flags(pool, project) == first

    def test_code_we_could_not_read_makes_a_missing_tool_only_a_review(self, pool, project):
        save_stage(pool, project, "github_check", GITHUB)
        save_stage(pool, project, "event_dates", {"found": False, "reason": "no repository link was given"})
        save_stage(pool, project, "sponsor_files", TOOLS)
        pages = self.pages()
        del pages[raw("app.js")]  # did not load
        run(pool, project, FetchFiles(pages))
        assert {l for t, l, r in flags(pool, project) if "Supabase" in r} == {"review"}

    def test_no_repository_means_nothing_is_flagged_and_the_reason_is_said(self, pool, project):
        save_stage(pool, project, "github_check", {"found": False, "reason": "no repository link was given"})
        save_stage(pool, project, "event_dates", {"found": False, "reason": "no repository link was given"})
        save_stage(pool, project, "sponsor_files", {"found": False, "reason": "no repository link was given", "tools": TOOLS["tools"]})
        fetch = FetchFiles({})
        out = run(pool, project, fetch)
        assert flags(pool, project) == [] and fetch.fetched == []
        assert out["sponsors"].startswith("not checked") and out["dates_not_checked"]

    def test_an_event_without_sponsor_tools_skips_that_part(self, pool, project):
        save_stage(pool, project, "github_check", GITHUB)
        save_stage(pool, project, "event_dates", {"found": True, "share_before_start_pct": 5.0})
        save_stage(pool, project, "sponsor_files", {"skipped": True, "reason": "the event lists no sponsor tools"})
        out = run(pool, project, FetchFiles({}))
        assert flags(pool, project) == [] and out["sponsors"] == "the event lists no sponsor tools"

    def test_a_resume_project_is_skipped(self, pool):
        set_services(Services(None, pool, None, None, None, lambda host: None, None))
        job = Job(str(uuid.uuid4()), "repo_checks", "python", "candidate_project", str(uuid.uuid4()), {}, "recruiter", 1, 1, 3, 60)
        assert stage_module.repo_checks(job, JobContext(job, pool))["skipped"]
        set_services(None)
