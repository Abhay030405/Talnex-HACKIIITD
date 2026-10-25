"""Stack detect and bring-up: from a GitHub link to an app that is running inside a VM (architecture 28.2 R2 and R3).

    result = prepare_and_run(vm, model, "https://github.com/a/b")
    result.status        # "running" or "could_not_run"
    result.reason        # a plain sentence when it could not run
    result.bringup.port  # where the app listens

A repo that cannot be reached, whose stack we cannot run, or whose build fails after the README steps and ONE
model-assisted fix ends as "could not run" with the last log lines as proof. It is never called "broken".
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from talnex_ai.llm.structured import ChatClient, StructuredError
from talnex_ai.sandbox.stack_detect.bringup import BringUp, RunnableVm, bring_up
from talnex_ai.sandbox.stack_detect.detect import RepoFacts, detect_recipe
from talnex_ai.sandbox.stack_detect.envvalues import service_env
from talnex_ai.sandbox.stack_detect.fix import propose_fix
from talnex_ai.sandbox.stack_detect.gather import REPO_DIR, RepoUnreachable, clean_github_url, clone, read_facts
from talnex_ai.sandbox.stack_detect.recipe import FULL_IMAGE, IMAGES, Recipe

__all__ = ["RunResult", "prepare_and_run", "Recipe", "REPO_DIR", "RepoFacts"]


@dataclass
class RunResult:
    status: str                      # running / could_not_run
    reason: str = ""
    url: str = ""
    recipe: Optional[Recipe] = None
    facts: Optional[RepoFacts] = None
    bringup: Optional[BringUp] = None
    attempts: list[BringUp] = field(default_factory=list)   # every try, the last one is `bringup`
    fix_used: bool = False
    # The VM that holds the running app. Set only when status is "running"; every other VM made here is destroyed.
    vm: Any = None

    @property
    def ok(self) -> bool:
        return self.status == "running"

    def build_log(self) -> str:
        return "\n\n=== next attempt ===\n\n".join(a.build_log() for a in self.attempts)


def _could_not_run(reason: str, **kw) -> RunResult:
    return RunResult(status="could_not_run", reason=reason, **kw)


def prepare_and_run(
    new_vm: Callable[[str], Any],
    model: Optional[ChatClient],
    repo_url: str,
    *,
    build_timeout_seconds: int = 600,
    start_timeout_seconds: int = 90,
    job_id: Optional[str] = None,
) -> RunResult:
    """`new_vm(image, services=...)` makes a fresh VM (it must have .exec, .request, .wait_for_port and .destroy).

    The repo is cloned into the shared base image, which has git, Node and Python, and read there. If it turns out to
    need a different image (a stack with its own image), that VM is replaced by the right one. A VM is returned (alive)
    only when the app is running; on any failure it is destroyed."""
    url = clean_github_url(repo_url)
    if url is None:
        return _could_not_run("the repository link is not a GitHub address", url=repo_url)

    vm = new_vm(FULL_IMAGE)
    try:
        result = _run_in(vm, new_vm, model, url, build_timeout_seconds, start_timeout_seconds, job_id)
    except BaseException:
        vm.destroy()
        raise
    if result.status != "running" and result.vm is None:
        vm.destroy()
    return result


def _run_in(vm, new_vm, model, url, build_timeout, start_timeout, job_id) -> RunResult:
    try:
        clone(vm, url)
    except RepoUnreachable as exc:
        return _could_not_run(f"repo not reachable: {exc}", url=url)
    facts = read_facts(vm)
    if not facts.files:
        return _could_not_run("the repository is empty", url=url, facts=facts)
    recipe = detect_recipe(facts)
    if recipe.stack == "unknown":
        return _could_not_run(recipe.notes[0] if recipe.notes else "the stack could not be worked out", url=url, facts=facts, recipe=recipe)

    # The first VM was made from the base image with no services. If the repo needs another image, or needs backing
    # stores (postgres, redis...) started beside it, replace it with a VM that has them, and clone again.
    if recipe.image != FULL_IMAGE or recipe.services:
        vm.destroy()
        vm = new_vm(recipe.image, services=list(recipe.services))
        try:
            clone(vm, url)
        except RepoUnreachable as exc:
            vm.destroy()
            return _could_not_run(f"repo not reachable: {exc}", url=url, facts=facts, recipe=recipe)
        # Point the app at the real services instead of the harmless fakes.
        if recipe.services:
            recipe = recipe.model_copy(update={"env": {**recipe.env, **service_env(recipe.services)}})

    result = RunResult(status="could_not_run", url=url, recipe=recipe, facts=facts)
    first = bring_up(vm, recipe, build_timeout_seconds=build_timeout, start_timeout_seconds=start_timeout)
    result.attempts.append(first)
    result.bringup = first

    if not first.ok and model is not None:
        try:
            fixed = propose_fix(model, recipe, first.failed_step, first.last_output(), facts, job_id=job_id)
        except StructuredError:
            fixed = None  # the model gave no usable answer: keep the first failure
        if fixed is not None:
            result.fix_used = True
            second = bring_up(vm, fixed, build_timeout_seconds=build_timeout, start_timeout_seconds=start_timeout)
            result.attempts.append(second)
            result.recipe, result.bringup = fixed, second

    # Listening but answering only with server errors (often a missing secret or database) is still up: test it anyway,
    # so the routes, tests and code review still run, and every 500 they meet is shown.
    if result.bringup.ok or result.bringup.failed_step == "health":
        result.status, result.vm = "running", vm
        return result
    result.reason = _explain_failure(result)
    vm.destroy()
    return result


def _explain_failure(result: RunResult) -> str:
    recipe, last = result.recipe, result.bringup
    assert recipe is not None and last is not None
    needs = f"; the app seems to need {', '.join(recipe.services)}, which the sandbox cannot start yet" if recipe.services else ""
    tried = " after the README steps and one automatic fix" if result.fix_used else ""
    return f"could not run{tried}: {last.reason}{needs}"
