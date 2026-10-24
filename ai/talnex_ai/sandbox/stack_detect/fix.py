"""The one model-assisted fix of a failed run recipe (architecture 28.5).

If the install, build or start fails, the model sees the recipe and the end of the log and proposes corrected commands.
It is allowed exactly one such fix per run. Its answer is validated, and only a fix that actually changes something is used."""
from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from talnex_ai.formats.parse import parse_model
from talnex_ai.llm.prompts.sandbox_recipe import SYSTEM, build_user
from talnex_ai.llm.structured import ChatClient, ask_json
from talnex_ai.sandbox.stack_detect.detect import RepoFacts, readme_commands
from talnex_ai.sandbox.stack_detect.recipe import Recipe

_SAFE_DIR = re.compile(r"^[A-Za-z0-9_./-]+$")


class RecipeFix(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    install_cmd: Optional[str] = Field(default=None, max_length=600)
    build_cmd: Optional[str] = Field(default=None, max_length=600)
    start_cmd: Optional[str] = Field(default=None, max_length=600)
    app_dir: Optional[str] = Field(default=None, max_length=200)
    port: Optional[int] = Field(default=None, ge=1, le=65535)
    env: Optional[dict[str, str]] = None
    explanation: str = Field(default="", max_length=400)


def propose_fix(client: ChatClient, recipe: Recipe, failed_step: str, output_tail: str, facts: RepoFacts,
                *, job_id: Optional[str] = None) -> Optional[Recipe]:
    """A corrected recipe, or None when the model has nothing useful to change."""
    readme = facts.text("README.md") or facts.text("readme.md") or facts.text("README")
    fix = ask_json(
        client, "agent", SYSTEM,
        build_user(recipe.model_dump_json(indent=1), failed_step, output_tail,
                   [*readme_commands(readme)["install"], *readme_commands(readme)["start"]], facts.files, readme=readme),
        lambda text: parse_model(RecipeFix, text), job_id=job_id, max_tokens=3000,
    )
    return apply_fix(recipe, fix, facts)


def apply_fix(recipe: Recipe, fix: RecipeFix, facts: RepoFacts) -> Optional[Recipe]:
    updates: dict = {}
    for name in ("install_cmd", "build_cmd", "start_cmd"):
        value = getattr(fix, name)
        if value is not None and value != getattr(recipe, name):
            updates[name] = value
    if fix.app_dir is not None and fix.app_dir != recipe.app_dir:
        directory = fix.app_dir.strip("/")
        known = directory == "" or any(f.startswith(directory + "/") for f in facts.files)
        if ".." in directory or (directory and not _SAFE_DIR.match(directory)) or not known:
            return None  # a folder that is not in the repo: refuse the whole fix rather than guess
        updates["app_dir"] = directory
    if fix.port is not None and fix.port != recipe.port:
        updates["port"] = fix.port
    if fix.env:
        merged = {**recipe.env, **fix.env}
        if merged != recipe.env:
            updates["env"] = merged
    if not updates:
        return None
    note = "model fix: " + (fix.explanation or "commands changed")
    return recipe.model_copy(update={**updates, "source": "model_fix", "confidence": "low", "notes": [*recipe.notes, note]})
