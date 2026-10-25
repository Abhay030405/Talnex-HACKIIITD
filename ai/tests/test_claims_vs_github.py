"""Resume claims against GitHub: dates and team read only from the text, and each comparison."""
import pytest

from talnex_ai.coding.claims_vs_github import add_claims, claimed_from_text, compare, github_facts, parse_dates
from talnex_ai.resume.reader import RawProject, RawResume, validate
from talnex_ai.settings import InsightSettings

CFG = InsightSettings()


@pytest.mark.parametrize("text,want", [
    ("Built it Jan 2026 – Mar 2026 with React", ("2026-01", "2026-03")),
    ("(2025 - Present)", ("2025", "present")),
    ("03/2026 to 06/2026", ("2026-03", "2026-06")),
    ("2024-11 — 2025-02", ("2024-11", "2025-02")),
    ("September '25 until now", ("2025-09", "present")),
    ("Shipped in 2023.", ("2023", "2023")),
    ("A chat app with sockets", (None, None)),
    ("Supports 1000 users", (None, None)),          # a number that is not a year
])
def test_dates_in_many_formats(text, want):
    assert parse_dates(text) == want


def test_the_model_cannot_invent_dates_team_or_role():
    got = claimed_from_text("A todo app in Go.", {"claimed_start": "2024-01", "claimed_end": "2024-06",
                                                  "claimed_team": "team", "claimed_role": "lead engineer"})
    assert got == {"start": None, "end": None, "team": None, "team_size": None, "role": None}
    got = claimed_from_text("Solo project, 2024. I was the lead engineer.", {"claimed_role": "lead engineer"})
    assert (got["start"], got["team"], got["role"]) == ("2024", "solo", "lead engineer")
    assert claimed_from_text("Built with a team of 4", {})["team_size"] == 4


def test_the_reader_keeps_claims_from_the_project_text_only():
    text = "Projects\nShelfMate — Jan 2026 – Mar 2026, solo\nA book tracker.\nNoteBox\nA notes app built by a team of 3."
    raw = RawResume(projects=[RawProject(name="ShelfMate", bullets=["A book tracker."]),
                              RawProject(name="NoteBox", bullets=["A notes app built by a team of 3."], claimed_start="2020")])
    shelf, notes = validate(raw, text).projects
    assert shelf.claims == {"start": "2026-01", "end": "2026-03", "team": "solo"}
    assert notes.claims == {"team": "team", "team_size": 3}    # the model's 2020 is not in NoteBox's text


def facts(dates, people):
    return {"commit_dates": dates, "contributors": [{"login": a, "commits": n} for a, n in people],
            "first_commit": dates[0] if dates else None, "last_commit": dates[-1] if dates else None}


def kinds(found):
    return {f["signal"]: f["evidence"]["tone"] for f in found}


def test_dates_match_or_fall_outside():
    inside = facts(["2026-01-10T00:00:00Z", "2026-02-02T00:00:00Z", "2026-03-20T00:00:00Z"], [("asha", 3)])
    assert kinds(compare({"start": "2026-01", "end": "2026-03"}, inside, "asha", CFG))["claimed_dates"] == "strength"
    outside = facts(["2024-05-01T00:00:00Z", "2024-05-02T00:00:00Z", "2026-02-01T00:00:00Z"], [("asha", 3)])
    found = compare({"start": "2026-01", "end": "2026-03"}, outside, "asha", CFG)
    assert kinds(found)["claimed_dates"] == "look" and "2 of 3 commits fall outside" in found[0]["evidence"]["summary"]


def test_solo_claim_with_other_contributors_and_a_small_own_share():
    f = facts(["2026-01-01T00:00:00Z"] * 10, [("ravi", 8), ("asha", 2)])
    found = compare({"team": "solo"}, f, "asha", CFG)
    assert kinds(found) == {"claimed_team": "look", "own_share": "look"}
    assert "ravi 80%" in found[0]["evidence"]["summary"]
    assert kinds(compare({"team": "team"}, f, "asha", CFG))["claimed_team"] == "neutral"


def test_an_unknown_account_is_said_not_guessed():
    found = compare({}, facts(["2026-01-01T00:00:00Z"], [("asha", 1)]), None, CFG)
    assert kinds(found) == {"own_share": "neutral"} and "not known" in found[0]["evidence"]["summary"]


def test_months_claimed_but_commits_in_one_burst():
    burst = facts(["2026-01-05T01:00:00Z"] * 9 + ["2026-04-01T00:00:00Z"], [("asha", 10)])
    assert kinds(compare({"start": "2026-01", "end": "2026-04"}, burst, "asha", CFG))["claimed_effort"] == "look"


class FakeGitHub:
    def __init__(self, fail=False):
        self.fail, self.calls = fail, []

    def _get(self, path, **params):
        self.calls.append((path, params))
        if self.fail:
            raise RuntimeError("GitHub could not read (403)")
        if path.endswith("/contributors"):
            return [{"login": "asha", "contributions": 2}]
        return [{"commit": {"author": {"date": "2026-02-01T00:00:00Z"}}},
                {"commit": {"author": {"date": "2026-01-01T00:00:00Z"}}}]


def test_facts_and_report_fill_in_and_a_failure_is_could_not_check():
    gh = FakeGitHub()
    got = github_facts(gh, "asha/shelf", 3)
    assert (got["first_commit"], got["last_commit"], got["commit_count"]) == ("2026-01-01T00:00:00Z", "2026-02-01T00:00:00Z", 2)
    report = {"projects": [{"id": "p1", "name": "Shelf", "repo_url": "https://github.com/asha/shelf"}], "profile_insights": []}
    add_claims(report, {"p1": {"start": "2026-01", "end": "2026-02"}}, gh, {"p1": "asha"}, CFG, 3,
               lambda u: "asha/shelf" if u else None)
    block = report["projects"][0]["claims_vs_github"]
    assert block["actual"]["first_commit"] and "commit_dates" not in block["actual"]
    assert {i["signal"] for i in report["profile_insights"]} >= {"claimed_dates", "own_share"}
    bad = {"projects": [{"id": "p1", "name": "Shelf", "repo_url": "x"}], "profile_insights": []}
    add_claims(bad, {}, FakeGitHub(fail=True), {}, CFG, 3, lambda u: "asha/shelf")
    assert bad["projects"][0]["claims_vs_github"]["actual"] is None and bad["profile_insights"] == []
