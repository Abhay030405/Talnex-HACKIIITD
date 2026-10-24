"""Build and start a repo from its recipe, inside a VM that already holds the cloned code (architecture 28.5).

Install, optional build, start in the background, wait for a port, then probe a few health paths. Every step records the
command, its exit code and the end of its output, which is the proof shown for "could not run". A build or start that
fails is NEVER "broken": setup failures end as "could not run" (architecture 28.10).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Optional, Protocol

from talnex_ai.sandbox.client import ExecResult, HttpResult
from talnex_ai.sandbox.stack_detect.gather import REPO_DIR
from talnex_ai.sandbox.stack_detect.recipe import Recipe

APP_LOG = "/tmp/app.log"
LOG_TAIL_LINES = 80


class RunnableVm(Protocol):
    def exec(self, command: str, **kwargs) -> ExecResult: ...
    def wait_for_port(self, *, timeout_seconds: int = 60, port: Optional[int] = None, poll_seconds: float = 1.0) -> Optional[int]: ...
    def request(self, method: str, port: int, path: str, **kwargs) -> HttpResult: ...


@dataclass
class StepLog:
    name: str          # install, build, start
    command: str
    exit_code: int
    timed_out: bool
    output_tail: str


@dataclass
class BringUp:
    ok: bool
    failed_step: str = ""            # install, build, start, health ("" when ok)
    reason: str = ""                 # a plain sentence for the person reading the result
    port: Optional[int] = None
    health_path: str = ""
    health_status: int = 0
    steps: list[StepLog] = field(default_factory=list)
    app_log_tail: str = ""

    def build_log(self) -> str:
        """The install and build steps as one readable text, for the proof file."""
        parts = []
        for s in self.steps:
            parts.append(f"$ {s.command}\n[exit {s.exit_code}{', timed out' if s.timed_out else ''}]\n{s.output_tail}")
        return "\n\n".join(parts)

    def last_output(self) -> str:
        return (self.steps[-1].output_tail if self.steps else "") + (("\n" + self.app_log_tail) if self.app_log_tail else "")


def _tail(text: str, lines: int = LOG_TAIL_LINES) -> str:
    return "\n".join(text.strip().splitlines()[-lines:])


def bring_up(
    vm: RunnableVm,
    recipe: Recipe,
    *,
    build_timeout_seconds: int = 600,
    start_timeout_seconds: int = 90,
    sleep: Callable[[float], None] = time.sleep,
) -> BringUp:
    """Run the recipe. Returns what happened; never raises for a failed command."""
    workdir = f"{REPO_DIR}/{recipe.app_dir}" if recipe.app_dir else REPO_DIR
    out = BringUp(ok=False)
    if not recipe.start_cmd:
        out.failed_step, out.reason = "start", "no way to start the app was found"
        return out

    for name, command in (("install", recipe.install_cmd), ("build", recipe.build_cmd)):
        if not command:
            continue
        res = vm.exec(command, workdir=workdir, env=recipe.env, timeout_seconds=build_timeout_seconds)
        out.steps.append(StepLog(name, command, res.exit_code, res.timed_out, _tail(res.output)))
        if not res.ok:
            out.failed_step = name
            out.reason = (f"the {name} step ran out of time" if res.timed_out
                          else f"the {name} step failed (exit {res.exit_code})")
            return out

    vm.exec(f"({recipe.start_cmd}) > {APP_LOG} 2>&1", workdir=workdir, env=recipe.env, detach=True)
    out.steps.append(StepLog("start", recipe.start_cmd, 0, False, "started in the background"))
    port = vm.wait_for_port(timeout_seconds=start_timeout_seconds, port=recipe.port)
    out.app_log_tail = _tail(vm.exec(f"tail -n {LOG_TAIL_LINES} {APP_LOG} 2>/dev/null || true", timeout_seconds=15).stdout)
    if port is None:
        out.failed_step = "start"
        out.reason = (f"nothing started listening on port {recipe.port}" if recipe.port
                      else f"the app did not start listening on any port within {start_timeout_seconds} s")
        return out
    out.port = port

    # "Healthy" means the app answers with anything below 500: a 404 on "/" still proves it is up.
    for path in recipe.health_paths:
        res = vm.request("GET", port, path, timeout_seconds=10)
        if res.answered and res.status < 500:
            out.health_path, out.health_status = path, res.status
            out.ok = True
            return out
    out.failed_step, out.reason = "health", "the app is listening but none of the health paths answered without a server error"
    return out
