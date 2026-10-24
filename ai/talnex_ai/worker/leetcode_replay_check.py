"""Read and judge one LeetCode user's Code Replay pastes, without the database or the website.

    python -m talnex_ai.worker.leetcode_replay_check --user van_zhang [--contest weekly-contest-524]

Without --contest it picks contests from the user's history like the stage does. Needs LEETCODE_GRAPHQL_URL.
"""
from __future__ import annotations

import argparse
import sys

from talnex_ai import settings as settings_module
from talnex_ai.coding.leetcode_capture import check_replays
from talnex_ai.coding.leetcode_capture.same_code import bql_neighbours


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--user", required=True)
    parser.add_argument("--contest", action="append", help="contest slug; repeat for more")
    args = parser.parse_args()
    cfg = settings_module.load()
    if not cfg.leetcode_graphql_url:
        print("set LEETCODE_GRAPHQL_URL first")
        return 2
    near = bql_neighbours(cfg.browserless_bql_url, cfg.browserless_token) if cfg.browserless_bql_url and cfg.browserless_token else None
    result = check_replays(cfg.leetcode_graphql_url, args.user, cfg.leetcode_replay, contests=args.contest, neighbours=near)
    print(f"contests: {', '.join(result['contests_checked']) or 'none'} | replays read: {result['replays_read']} | "
          f"pastes: {len(result['pastes'])} | suspicious: {result['suspicious']}")
    for r in result["pastes"]:
        p = r["paste"]
        print(f"[{r['weight']}] {r['contest']} / {r['problem']} at {p.at_s // 60:02d}:{p.at_s % 60:02d}: {r['reason']}")
        if r.get("same_code"):
            print(f"    same code check: {r['same_code']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
