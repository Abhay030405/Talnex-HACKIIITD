"""Copying between teams (architecture section 12): read each team's repo as a fingerprint, compare every pair after removing
starter code, and let a model look at the top matching files before anything is flagged.

`fingerprint.py` runs inside a throwaway VM (stdlib only), `compare.py` is plain code, this file does the VM and model work.
"""
from __future__ import annotations

import base64
import json
import shlex
from pathlib import Path
from typing import Any, Optional, Protocol, Sequence

from pydantic import BaseModel, ConfigDict, Field

from talnex_ai.formats.parse import parse_model
from talnex_ai.llm.prompts.copy_check import SYSTEM, VERDICTS, build_user
from talnex_ai.llm.structured import ChatClient, ask_json
from talnex_ai.sandbox.client import ExecResult
from talnex_ai.sandbox.stack_detect.gather import REPO_DIR, RepoUnreachable, clean_github_url, clone

_SCRIPT = Path(__file__).with_name("fingerprint.py")
_FILE_MARK = "@@@TALNEX-COPY-FILE"
LOOK_FILE_BYTES = 6000


class VmLike(Protocol):
    def exec(self, command: str, **kwargs: Any) -> ExecResult: ...


def fingerprint_repo(vm: VmLike, url: str) -> dict[str, list[int]]:
    """Clone the repo into the VM, run the fingerprint script there, and return {path: hashes}. Raises RepoUnreachable."""
    clone(vm, url)
    encoded = base64.b64encode(_SCRIPT.read_bytes()).decode()
    res = vm.exec(f"echo {encoded} | base64 -d > /tmp/fingerprint.py && python3 /tmp/fingerprint.py {REPO_DIR}", timeout_seconds=180)
    if res.exit_code != 0:
        raise RepoUnreachable(f"the code could not be read ({(res.stderr or '').strip()[-200:] or 'the fingerprint failed'})")
    try:
        return {p: [int(h) for h in hs] for p, hs in json.loads(res.stdout)["files"].items()}
    except (ValueError, KeyError, TypeError) as exc:
        raise RepoUnreachable(f"the fingerprint could not be read ({type(exc).__name__})") from exc


def read_pair_files(vm: VmLike, url_a: str, url_b: str, files: Sequence[tuple[str, str]]) -> list[tuple[str, str]]:
    """Clone both repos side by side and read the named files: `files` is (a_file, b_file); returns their texts."""
    outs = []
    for tag, url in (("a", url_a), ("b", url_b)):
        clean = clean_github_url(url)
        if clean is None:
            raise RepoUnreachable("the repository link is not a GitHub address")
        res = vm.exec(f"rm -rf /work/{tag} && GIT_TERMINAL_PROMPT=0 git clone --depth 1 --quiet {shlex.quote(clean)} /work/{tag}", timeout_seconds=240)
        if res.exit_code != 0:
            raise RepoUnreachable("a repository could not be cloned")
        outs.append(tag)
    texts: list[tuple[str, str]] = []
    for a_file, b_file in files:
        got = []
        for tag, f in (("a", a_file), ("b", b_file)):
            res = vm.exec(f"head -c {LOOK_FILE_BYTES} /work/{tag}/{shlex.quote(f)}", timeout_seconds=30)
            got.append(res.stdout if res.exit_code == 0 else "")
        texts.append((got[0], got[1]))
    return texts


class PairLook(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)
    verdict: str = "unclear"
    reason: str = Field(default="", max_length=900)
    evidence: list[str] = Field(default_factory=list, max_length=6)


def look_at_pair(model: ChatClient, team_a: str, team_b: str, shared_pct: float,
                 matches: Sequence[tuple[str, str, str, str, float]], *, job_id: Optional[str] = None) -> PairLook:
    look = ask_json(model, "copy_review", SYSTEM, build_user(team_a, team_b, shared_pct, matches), lambda t: parse_model(PairLook, t),
                    job_id=job_id, max_tokens=1200, temperature=0.0)
    if look.verdict not in VERDICTS:
        look.verdict = "unclear"
    return look


def lower(level: Optional[str]) -> Optional[str]:
    """One step less serious: strong -> review -> info."""
    return {"strong": "review", "review": "info"}.get(level or "", level)
