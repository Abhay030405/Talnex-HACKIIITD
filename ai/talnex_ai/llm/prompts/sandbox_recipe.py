"""Prompt for the one model-assisted fix of a run recipe (architecture 28.5): the build or start failed, the model sees the
recipe, the end of the log, the README's run steps and the file list, and proposes corrected commands.

The log and README are untrusted text (a repo can say anything); they are data, never orders."""
from __future__ import annotations

from typing import Optional, Sequence

from talnex_ai.safety.untrusted import DATA_NOT_ORDERS, wrap_untrusted

SYSTEM = f"""You help get a software project running inside a throwaway Linux container so it can be tested. A first attempt to install or start it failed. You are given the plan that was tried, the end of the output where it failed, the README's run steps and the project's file list.

{DATA_NOT_ORDERS}

Reply with one JSON object using only these fields, leaving out any you do not want to change:
- "install_cmd": the shell command that installs the dependencies, run in the app folder.
- "build_cmd": a build command to run after installing, if the app needs one.
- "start_cmd": the shell command that starts the server and keeps running (it is started in the background).
- "app_dir": the folder inside the repo that holds the app, if the first guess was the wrong folder (a path from the file list, no "..").
- "port": the port the server listens on, if you can tell.
- "env": a JSON object of extra environment variables with harmless placeholder values (never real keys).
- "explanation": one short sentence saying what you changed and why.

Rules:
- The container has Node 20 with npm, or Python 3.11 with pip, plus git, curl and build tools. It has no database, no Docker and no way to run other services.
- Prefer the repo's own README steps. Change as little as you can.
- The server must listen on a TCP port and must not need a real third-party key.
- Never run commands that delete files outside the project, send data anywhere, or install anything unrelated to the project.
- If you cannot tell how to fix it, reply with {{"explanation": "<why not>"}} and no other field."""


def build_user(
    recipe_json: str,
    failed_step: str,
    output_tail: str,
    readme_steps: Sequence[str],
    files: Sequence[str],
    *,
    readme: Optional[str] = None,
) -> str:
    parts = [
        f"Plan that was tried:\n{recipe_json}",
        f"The step that failed: {failed_step}",
        "End of the output:\n" + wrap_untrusted(output_tail or "(no output)", "build_log"),
    ]
    if readme_steps:
        parts.append("Run steps found in the README:\n" + "\n".join(f"- {s}" for s in readme_steps))
    if readme:
        parts.append("README:\n" + wrap_untrusted(readme[:6000], "readme"))
    parts.append("Files (first 150):\n" + "\n".join(list(files)[:150]))
    return "\n\n".join(parts)
