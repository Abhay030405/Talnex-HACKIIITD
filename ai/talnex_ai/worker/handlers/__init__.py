"""Importing this package registers every Python stage. A new stage module is added here."""
from talnex_ai.coding import register as _coding  # noqa: F401  (codechef, leetcode)
from talnex_ai.worker.handlers import selftest  # noqa: F401  (the queue self-test)

# Shared by both modes: claims, the live test track, scoring. Each works for a project and a resume project alike.
from talnex_ai.worker.handlers import claims, precheck, test_plan, live_test, proof_check, feature_score  # noqa: F401
from talnex_ai.worker.handlers import track_reconcile, project_score  # noqa: F401

# The sandbox track: run the repository, find its routes, test them, review the code.
from talnex_ai.worker.handlers import sandbox_run, route_discovery, sandbox_plan, sandbox_test, sandbox_end  # noqa: F401
from talnex_ai.worker.handlers import repo_tests, repo_checks, code_review  # noqa: F401

# Hackathon projects: video, originality, the proof card; then the event-level checks.
from talnex_ai.worker.handlers import video_read, originality, not_built_yet, project_report  # noqa: F401
from talnex_ai.worker.handlers import copy_between_teams, feature_compare, ai_opinion  # noqa: F401

# Recruiter: the resume, each project's summary, the proof report.
from talnex_ai.worker.handlers import resume_read, project_summary, candidate_report  # noqa: F401

# Authorship proof and the voice walkthrough.
from talnex_ai.worker.handlers import authorship_read, code_locate, walkthrough_answer  # noqa: F401

# Ask TalNex: a recruiter question answered from the saved report.
from talnex_ai.worker.handlers import report_answer  # noqa: F401
