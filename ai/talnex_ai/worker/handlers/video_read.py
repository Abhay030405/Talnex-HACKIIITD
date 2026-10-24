"""Stage `video_read`: read the demo video for the features it shows (hackathon projects).

The video reader isn't built yet. Until it is, this stage ends as "skipped" with that reason, so
the claims stage still starts and uses the organizer's criteria. A video that exists but wasn't
read is said so in the result, never ignored quietly.
"""
from __future__ import annotations

from typing import Any, Mapping

from talnex_ai.db.jobs import Job
from talnex_ai.worker.registry import JobContext, stage
from talnex_ai.worker.subjects import load_subject_info, set_status, subject_of


@stage("video_read")
def video_read(job: Job, ctx: JobContext) -> Mapping[str, Any]:
    info = load_subject_info(ctx.pool, subject_of(job))
    set_status(ctx.pool, info, "reading")
    if not info.video_url:
        return {"skipped": True, "reason": "no demo video was given"}
    return {"skipped": True, "reason": "the video reader is not built yet, so the video was not read",
            "video_url": info.video_url}
