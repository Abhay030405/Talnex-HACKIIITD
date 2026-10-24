"""Where each kind of file lives in the bucket.

The Go API builds the same paths in backend/internal/storage/r2/keys.go to hand out view
links, so any change here must be made there too.
"""
from __future__ import annotations


def _join(*parts: object) -> str:
    """Join path parts, refusing anything that could escape its folder or collide with another key."""
    out = []
    for part in parts:
        text = str(part)
        if not text or "/" in text or "\\" in text or text in (".", ".."):
            raise ValueError(f"bad storage key part: {text!r}")
        out.append(text)
    return "/".join(out)


def screen_key(project: str, run: str, step: int) -> str:
    return _join("screens", project, run, step)


def live_screen_key(subject: str, run: str) -> str:
    """The newest live-view frame of one test run, overwritten each time (the Go API only makes view links)."""
    return _join("live", subject, run, "screen.jpg")


def video_key(project: str, name: str) -> str:
    return _join("videos", project, name)


def frame_key(project: str, name: str) -> str:
    return _join("frames", project, name)


def resume_key(candidate: str, name: str) -> str:
    return _join("resumes", candidate, name)


def resume_prefix(candidate: str) -> str:
    return _join("resumes", candidate) + "/"


def replay_key(candidate: str, contest: str, problem: str) -> str:
    return _join("replays", candidate, contest, problem)


def sandbox_key(project: str, run: str, name: str) -> str:
    return _join("sandbox", project, run, name)


def voice_key(owner: str, walkthrough: str) -> str:
    return _join("voice", owner, walkthrough)


def opinion_key(project: str, name: str) -> str:
    return _join("opinion", project, name)
