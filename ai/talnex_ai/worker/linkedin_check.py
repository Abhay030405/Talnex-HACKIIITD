"""Log in to the team LinkedIn account through Browserless BQL and check one candidate profile, without the website.

    python -m talnex_ai.worker.linkedin_check --profile https://www.linkedin.com/in/someone

Needs BROWSERLESS_BQL_URL, BROWSERLESS_TOKEN, LINKEDIN_EMAIL and LINKEDIN_PASSWORD. Prints whether the profile exists
and the name on it. Never prints the password or cookies.
"""
from __future__ import annotations

import argparse
import sys

from talnex_ai import settings as settings_module
from talnex_ai.browser.linkedin import LinkedInClient


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", required=True)
    args = parser.parse_args()
    cfg = settings_module.load()
    if not (cfg.browserless_bql_url and cfg.browserless_token and cfg.linkedin_email and cfg.linkedin_password):
        print("set BROWSERLESS_BQL_URL, BROWSERLESS_TOKEN, LINKEDIN_EMAIL and LINKEDIN_PASSWORD first")
        return 2
    li = LinkedInClient(cfg.browserless_bql_url, cfg.browserless_token)
    session = li.login(cfg.linkedin_email, cfg.linkedin_password)
    if not session.ok:
        print(f"could not log in to LinkedIn: {session.reason}")
        return 1
    r = li.check_profile(session, args.profile)
    print(f"{r.status}: {r.name or '-'} ({r.url})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
