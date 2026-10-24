"""The repo_quality checks: plain-code areas on fake repos, the role level rule, and evidence that must exist."""
from types import SimpleNamespace

from talnex_ai.checks import repo_quality as rq
from talnex_ai.worker.handlers.repo_quality import consistency, read_facts

GOOD_PATHS = ["README.md", "LICENSE", ".gitignore", ".env.example", "package.json", "package-lock.json", "tsconfig.json",
              ".eslintrc.json", ".github/workflows/ci.yml", "Dockerfile", "openapi.yaml",
              "src/server.ts", "src/routes/users.ts", "src/routes/users.test.ts", "src/db.ts", "tests/api.test.ts"]
README = ("# App\n\n## Getting started\nInstall with npm install.\n\n## Usage\nRun npm start.\n\n"
          "## Configuration\nCopy .env.example to .env and set DATABASE_URL.\n" + "More text. " * 40)


def commit(sha, msg, date):
    return {"sha": sha * 7, "message": msg, "date": date, "author": "a"}


GOOD_COMMITS = [commit("a", "feat(users): add sign up with email check", "2026-03-01T10:00:00Z"),
                commit("b", "fix(db): close the pool on shutdown", "2026-03-05T10:00:00Z"),
                commit("c", "test: cover the users route", "2026-03-09T10:00:00Z"),
                commit("d", "docs: explain the env settings", "2026-03-12T10:00:00Z")]


def good():
    return rq.RepoFacts(
        paths=GOOD_PATHS, sizes={p: 2000 for p in GOOD_PATHS},
        files={"README.md": README, "package.json": '{"dependencies": {"express": "4"}}',
               "tsconfig.json": '{ "compilerOptions": { "strict": true } }',
               ".github/workflows/ci.yml": "steps:\n  - run: npm test\n"},
        commits=GOOD_COMMITS, branches=3, readme_path="README.md", sandbox={"status": "running", "recipe_source": "readme"})


def messy():
    paths = ["main.py", "node_modules/x/index.js", ".env"] + [f"f{i}.py" for i in range(18)]
    return rq.RepoFacts(paths=paths, sizes={**{p: 500 for p in paths}, "main.py": 90_000},
                        files={".env": "API_KEY=sk_live_1234567890abcdef\n"},
                        commits=[commit(c, m, "2026-03-01T1%d:00:00Z" % i) for i, (c, m) in
                                 enumerate([("a", "fix"), ("b", "update"), ("c", "wip"), ("d", "fix"), ("e", "changes")])],
                        branches=1, readme_path=None)


def test_a_well_built_repo_scores_high_in_every_area():
    result = rq.judge(good(), "mid")
    scores = {a["area"]: a["score"] for a in result["areas"]}
    assert set(scores) == {"production", "structure", "hygiene", "commits", "docs"}
    assert all(s >= 7 for s in scores.values()), scores
    assert result["overall"] >= 8


def test_a_messy_repo_is_called_out_with_real_evidence():
    f = messy()
    prod, struct, hyg, com = rq.production(f, "mid"), rq.structure(f, "mid"), rq.hygiene(f, "mid"), rq.commits_area(f, "mid")
    assert prod.score < 4 and any(e["path"] == ".env" for e in prod.evidence)
    assert "no tests" in prod.summary
    assert struct.score <= 5 and any("node_modules" in e["path"] for e in struct.evidence)
    assert any(e["path"] == "main.py" for e in struct.evidence)          # the giant file
    assert hyg.score < 4 and "No README" in hyg.summary
    assert com.score < 4 and "100% say little" in com.summary


def test_a_fresher_is_never_marked_down_for_missing_enterprise_practices():
    f = rq.RepoFacts(paths=["README.md", "app.py", "test_app.py", "requirements.txt", "poetry.lock", ".env.example"],
                     files={}, commits=GOOD_COMMITS, readme_path="README.md")
    assert rq.production(f, "fresher").score > rq.production(f, "senior").score
    assert rq.production(f, "fresher").score >= 8


def test_evidence_that_does_not_exist_is_dropped():
    f = good()
    area = rq.Area("production", 5, "x", [rq.file_evidence("src/server.ts", "real"), rq.file_evidence("made/up.ts", "fake"),
                                         {"kind": "commit", "sha": "zzzzzzz", "message": "x", "note": "fake"},
                                         {"kind": "commit", "sha": "aaaaaaa", "message": "x", "note": "real"}])
    kept = rq.keep_real(area, f)
    assert [e.get("path") or e.get("sha") for e in kept.evidence] == ["src/server.ts", "aaaaaaa"]


def test_docs_area_only_when_it_applies_and_reflects_the_vm():
    plain = rq.RepoFacts(paths=["README.md", "index.html"], files={}, readme_path="README.md")
    assert rq.docs_area(plain, "mid") is None
    failed = rq.RepoFacts(paths=["README.md", "requirements.txt"], files={"requirements.txt": "flask"},
                          readme_path="README.md", sandbox={"status": "could_not_run"})
    area = rq.docs_area(failed, "mid")
    assert area.score < 5 and "could not be started" in area.summary


def test_read_facts_respects_the_limits():
    tree = ["README.md", "package.json"] + [f"src/f{i}.ts" for i in range(40)]
    asked = []

    class Gh:
        def tree(self, repo):
            return tree, {p: 1000 + i for i, p in enumerate(tree)}, "main"

        def file(self, repo, path):
            asked.append(path)
            return "x" * 3000

        def commit_list(self, repo, n):
            return GOOD_COMMITS[:n]

        def branch_count(self, repo):
            return 2

    cfg = SimpleNamespace(max_files=10, max_bytes=9000, max_commits=2)
    facts = read_facts(Gh(), "o/r", cfg, None)
    assert len(asked) == 3 and asked[:2] == ["README.md", "package.json"]   # stopped at the byte budget
    assert len(facts.commits) == 2 and facts.branches == 2 and facts.readme_path == "README.md"


def test_the_model_view_keeps_only_paths_it_was_shown(monkeypatch):
    import talnex_ai.worker.handlers.repo_quality as stage

    f = rq.RepoFacts(paths=["src/a.ts", "src/b.ts"], files={"src/a.ts": "a" * 200, "src/b.ts": "b" * 100})
    answer = stage._Judgement(score=6, summary="Mixed error handling.",
                              evidence=[stage._Evidence(path="src/a.ts", note="catches errors"),
                                        stage._Evidence(path="src/ghost.ts", note="invented")])
    monkeypatch.setattr(stage, "ask_json", lambda *a, **k: answer)
    area = consistency(object(), f, "mid", 6, "job")
    assert area.area == "consistency" and [e["path"] for e in area.evidence] == ["src/a.ts"]
