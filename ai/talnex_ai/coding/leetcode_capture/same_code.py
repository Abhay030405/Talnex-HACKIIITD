"""Same pasted code as other contestants (architecture section 18, Strong): compare a suspicious paste with the final
code of the people who finished near the candidate in the same contest.

Leaked contest solutions spread in bursts, so the people who share one finish close together. The ranking pages around
the candidate's own row give those people's submission ids (one Browserless session: the ranking API sits behind a
Cloudflare check); their final code is public at `/api/submissions/<id>/`. Code is compared with the copy detector's
fingerprint, which ignores names, numbers, strings, comments and spacing. Nothing about the other contestants is saved:
only how many matched and how closely.
"""
from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Mapping, Optional

from talnex_ai.checks.copy_between_teams.fingerprint import fingerprint_text

log = logging.getLogger("talnex.coding")

SUBMISSION_URL = "https://leetcode.com/api/submissions/{}/"
SUFFIX = {"python": ".py", "python3": ".py", "java": ".java", "cpp": ".cpp", "c": ".c", "golang": ".go", "javascript": ".js",
          "typescript": ".ts", "csharp": ".cs", "kotlin": ".kt", "rust": ".rs", "swift": ".swift", "ruby": ".rb", "php": ".php",
          "dart": ".dart", "scala": ".java"}
DOWNLOADERS = 8

# Runs inside the contest's ranking page: find the candidate's page by score then finish time (rank numbers drift),
# then hand back who solved this question on the pages around it.
NEAR_JS = """(async () => {
  const S = __SCORE__, F = __FINISH__, QID = "__QID__", ME = "__ME__", SPREAD = __PAGES__;
  const page = async p => { const r = await fetch(`/contest/api/ranking/__CONTEST__/?pagination=${p}&region=global_v2`);
    if (r.status !== 200) throw new Error(`ranking page ${p} answered ${r.status}`); return r.json(); };
  const first = await page(1);
  const before = r => r.score > S || (r.score === S && r.finish_time < F);
  let lo = 1, hi = Math.max(1, Math.ceil(first.user_num / 25));
  while (lo < hi) { const mid = Math.floor((lo + hi + 1) / 2); const d = await page(mid);
    if (d.total_rank.length && before(d.total_rank[0])) lo = mid; else hi = mid - 1; }
  const out = [];
  for (let p = Math.max(1, lo - SPREAD); p <= lo + SPREAD; p++) {
    for (const r of (await page(p)).total_rank || []) {
      const s = (r.submissions || {})[QID];
      if (s && (r.user_slug || "").toLowerCase() !== ME) out.push({id: s.submission_id, lang: s.lang});
    }
  }
  return JSON.stringify(out);
})()"""

NEAR_QUERY = """
mutation TalnexNear($js: String!) {
  goto(url: "https://leetcode.com/contest/__CONTEST__/ranking/", waitUntil: domContentLoaded) { status }
  cf: solve { found solved }
  near: evaluate(content: $js, timeout: 240000) { value }
}"""


def containment(paste: list[int], other: list[int]) -> float:
    """How much of the paste's fingerprint is in the other code, 0..100."""
    if not paste:
        return 0.0
    return 100.0 * len(set(paste) & set(other)) / len(set(paste))


def score_of(replays: Mapping[str, list], credits: Mapping[str, int]) -> int:
    """The candidate's contest score: the credit of every question with an accepted submit (status 10) in its replay."""
    total = 0
    for slug, events in replays.items():
        for e in events or []:
            if e.get("eventType") != "5":
                continue
            try:
                accepted = (json.loads(e.get("eventData") or "{}").get("result") or {}).get("status") == 10
            except ValueError:
                accepted = False
            if accepted:
                total += credits.get(slug, 0)
                break
    return total


def bql_neighbours(bql_url: str, token: str) -> Callable[..., list[dict]]:
    """A neighbour finder that runs the ranking walk in one Browserless BQL session."""
    def find(contest: str, question_id: str, score: int, finish: int, me: str, pages: int) -> list[dict]:
        from talnex_ai.browser.bql import run_bql
        js = (NEAR_JS.replace("__SCORE__", str(score)).replace("__FINISH__", str(finish)).replace("__QID__", str(question_id))
              .replace("__ME__", me.lower()).replace("__PAGES__", str(pages)).replace("__CONTEST__", contest))
        data = run_bql(bql_url, token, NEAR_QUERY.replace("__CONTEST__", contest), {"js": js})
        return json.loads(data["near"]["value"])
    return find


def default_code(submission_id: int) -> Optional[str]:
    """One public submission's final code, or None if it cannot be read."""
    import httpx

    try:
        resp = httpx.get(SUBMISSION_URL.format(submission_id), timeout=20, headers={"User-Agent": "talnex"})
        return resp.json().get("code") if resp.status_code == 200 else None
    except (httpx.HTTPError, ValueError):
        return None


def match_paste(text: str, lang: str, others: list[Mapping[str, Any]], *, min_pct: float,
                code: Callable[[int], Optional[str]] = default_code) -> dict[str, Any]:
    """How many of `others` (submission id + language) contain at least `min_pct` of the pasted code."""
    suffix = SUFFIX.get(lang, "." + lang)
    mine = fingerprint_text(text, suffix)
    if not mine:
        return {"compared": 0, "matches": 0, "best_pct": 0.0, "reason": "the paste is too short to compare"}
    same_lang = [o for o in others if o.get("lang") == lang]
    with ThreadPoolExecutor(DOWNLOADERS) as pool:
        codes = list(pool.map(lambda o: code(o["id"]), same_lang))
    pcts = [containment(mine, fingerprint_text(c, suffix)) for c in codes if c]
    return {"compared": len(pcts), "matches": sum(1 for p in pcts if p >= min_pct),
            "best_pct": round(max(pcts), 1) if pcts else 0.0}
