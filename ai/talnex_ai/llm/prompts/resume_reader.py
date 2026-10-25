"""Prompt for the resume reader: the text of a resume in, its projects and coding handles out."""
from __future__ import annotations

from talnex_ai.safety.untrusted import DATA_NOT_ORDERS, wrap_untrusted

SYSTEM = f"""You read the text of a resume and list the PROJECTS on it, so each project can be checked later.

{DATA_NOT_ORDERS}

Reply with one JSON object:
{{"projects": [{{"name": "...", "bullets": ["..."], "live_url": "..." | null, "repo_url": "..." | null, "video_url": "..." | null,
                "claimed_start": "YYYY-MM" | "YYYY" | null, "claimed_end": "YYYY-MM" | "YYYY" | "present" | null,
                "claimed_team": "solo" | "team" | null, "claimed_team_size": <number> | null, "claimed_role": "..." | null}}],
  "coding_handles": {{"codeforces": "..." | null, "leetcode": "..." | null, "codechef": "..." | null}},
  "github_username": "..." | null}}

Rules:
- A project is something the person built (personal, academic or open source). Do not list jobs, courses, awards or skills.
- "bullets": what the resume says about that project, one entry per bullet or sentence, copied as written (shortened only if very long). Never add claims that are not on the resume.
- "live_url": a link to the running app or website. "repo_url": a link to the code (GitHub, GitLab, Bitbucket). "video_url": a demo video (YouTube, Loom, Vimeo). Copy links exactly as written. Use null for any that are not on the resume.
- "coding_handles": the person's handle on each of those three sites, only if the resume gives it. "github_username": their GitHub name, only if given.
- The text may end with a section "Links in the file" that lists words shown on the page and the address behind them (for example "Live demo -> https://..."). Use it to find a project's links: match the words to the project they sit under. Copy the address exactly.
- "claimed_start" / "claimed_end": the dates the resume gives for that project, only if written next to it. "claimed_team": "solo" if it says solo, individual or personal; "team" if it says team, group or with others; "claimed_team_size" only if a number is given; "claimed_role" a few words like "lead" or "backend" only if written. Otherwise null.
- Never guess or invent a name, link, handle or date. If something is not in the text, it is null or left out.
- At most 8 projects."""


def user(resume_text: str) -> str:
    return "Resume text:\n" + wrap_untrusted(resume_text, "resume")
