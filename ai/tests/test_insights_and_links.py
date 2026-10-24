"""Profile links from the resume (links only) and the plain-code profile insights."""
from talnex_ai.coding.insights import build_insights, problem_mix, rating_trend
from talnex_ai.resume.reader import social_links_in
from talnex_ai.settings import InsightSettings

CFG = InsightSettings()

RESUME = """Asha Verma
asha.verma@gmail.com | +91 98765 43210 | (555) 123-4567
GitHub: github.com/asha-dev  LinkedIn -> https://www.linkedin.com/in/asha-verma-12/
Portfolio: https://asha.dev  Kaggle: kaggle.com/ashav  twitter.com/asha_codes
link -> https://github.com/features
"""


def test_profile_links_are_found_and_email_or_phone_never_are():
    links = social_links_in(RESUME)
    assert links["github"] == "https://github.com/asha-dev"
    assert links["linkedin"] == "https://www.linkedin.com/in/asha-verma-12"
    assert links["portfolio"] == "https://asha.dev"
    assert links["kaggle"] == "https://www.kaggle.com/ashav" and links["x"] == "https://x.com/asha_codes"
    stored = " ".join(links.values())
    assert "@" not in stored and "98765" not in stored and "123-4567" not in stored and "gmail" not in stored


def test_a_site_page_is_not_a_person():
    assert social_links_in("see https://github.com/features and twitter.com/intent") == {}


def months(*commits):
    return [{"month": f"2026-{i + 1:02d}", "commits": c} for i, c in enumerate(commits)]


def tones(github=None, leetcode=None, projects=()):
    signals = []
    if github is not None:
        signals.append({"site": "github", "signal": "github_profile", "evidence": github})
    if leetcode is not None:
        signals.append({"site": "leetcode", "signal": "leetcode_profile", "evidence": leetcode})
    return {i["signal"]: i["evidence"]["tone"] for i in build_insights(signals, projects, CFG)}


def test_quiet_and_sparse_accounts_are_worth_a_look_never_more():
    got = tones({"months": months(5, 9, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0), "active_months": 2, "longest_quiet_months": 10})
    assert got["activity_trend"] == "look" and got["consistency"] == "look"


def test_active_consistent_starred_collaborating_account_is_a_strength():
    got = tones({"months": months(*[10] * 12), "active_months": 12, "longest_quiet_months": 0, "stars": 40,
                 "most_starred": "a/b", "most_starred_stars": 30, "external_prs": 5})
    assert got == {"activity_trend": "strength", "consistency": "strength", "recognition": "strength",
                   "collaboration": "strength"}


def test_rating_trend_and_problem_mix():
    assert rating_trend("leetcode", [1500, 1550, 1620], CFG)["evidence"]["tone"] == "strength"
    assert rating_trend("codeforces", [1400, 1390, 1300], CFG)["evidence"]["tone"] == "look"
    assert rating_trend("leetcode", [1500, 1510], CFG) is None
    assert problem_mix({"solved_easy": 80, "solved_medium": 15, "solved_hard": 5}, CFG)["evidence"]["tone"] == "look"
    assert problem_mix({"solved_easy": 40, "solved_medium": 45, "solved_hard": 15}, CFG)["evidence"]["tone"] == "strength"


def test_languages_on_the_resume_with_no_public_repo_are_worth_asking():
    projects = [{"name": "Shop", "features": [{"text": "Checkout written in Rust and Python"}]}]
    got = build_insights([{"site": "github", "signal": "github_profile", "evidence": {"languages": {"Python": 3}}}],
                         projects, CFG)
    lang = next(i for i in got if i["signal"] == "resume_vs_github")
    assert lang["evidence"]["tone"] == "look" and lang["evidence"]["missing"] == ["Rust"]
