"""The guide agent: reads the code with three fixed tools and writes the tour plan (architecture section 32.3)."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Optional, Sequence

from talnex_ai.formats import FormatError, parse_json_block
from talnex_ai.formats.tour import TourPlan
from talnex_ai.llm.prompts.tour_guide import GUIDE_SYSTEM, guide_user, observation
from talnex_ai.llm.structured import ChatClient, ask_json
from talnex_ai.sandbox.code_vm import CodeReadError, CodeVm, Tool

log = logging.getLogger("talnex.tour")

TOOLS = ("list", "search", "read")
EXTRA_TURNS = 2  # turns allowed after the last tool call, to give the plan


class GuideError(RuntimeError):
    """The guide never gave a usable plan. The tour then says it could not finish reading the code."""


@dataclass(frozen=True)
class Turn:
    tool: Optional[Tool] = None
    plan: Optional[TourPlan] = None


def _whole(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def parse_turn(text: str) -> Turn:
    """One model reply: a tool call or the plan. Anything else is a format error the model is shown once."""
    data = parse_json_block(text)
    if not isinstance(data, dict):
        raise FormatError("reply with one JSON object: a tool call or a plan")
    if "plan" in data:
        try:
            return Turn(plan=TourPlan.model_validate(data["plan"]))
        except Exception as err:
            raise FormatError(f"the plan is not in the right shape: {str(err)[:200]}") from err
    name = str(data.get("tool") or "").lower()
    if name not in TOOLS:
        raise FormatError(f"give a tool ({', '.join(TOOLS)}) or a plan")
    start = _whole(data.get("start"), 1)
    return Turn(tool=Tool(name, path=str(data.get("path") or ""), text=str(data.get("text") or ""), start=start,
                          end=_whole(data.get("end"), start + 79)))


def describe(tool: Tool) -> str:
    if tool.name == "list":
        return tool.path or "the project"
    if tool.name == "search":
        return f'"{tool.text}"' + (f" in {tool.path}" if tool.path else "")
    return f"{tool.path} lines {tool.start} to {tool.end}"


def run_guide(client: ChatClient, code: CodeVm, *, question: str, claims: Sequence[str], has_live: bool,
              history: Sequence[str], max_calls: int, job_id: Optional[str] = None,
              on_read: Optional[Callable[[str, str], None]] = None,
              on_code_text: Optional[Callable[[str], None]] = None) -> TourPlan:
    """Let the guide read until it gives the plan. `on_read(tool, what)` reports each read to the page and
    `on_code_text(text)` hands every piece of code read to the hidden-instruction check."""
    observations: list[str] = []
    calls = 0
    for _ in range(max_calls + EXTRA_TURNS):
        turn = ask_json(
            client, "tour_guide", GUIDE_SYSTEM,
            guide_user(question=question, claims=claims, has_live=has_live, history=history, observations=observations,
                       calls_left=max_calls - calls),
            parse_turn, job_id=job_id, temperature=0.1)
        if turn.plan is not None:
            return turn.plan
        tool = turn.tool
        if calls >= max_calls:
            observations.append("No tool calls are left. Give the plan now.")
            continue
        calls += 1
        if on_read:
            on_read(tool.name, describe(tool))
        try:
            output = code.run(tool)
        except CodeReadError as err:
            observations.append(observation(tool.name, describe(tool), f"that did not work: {err}"))
            continue
        if on_code_text:
            on_code_text(output)
        observations.append(observation(tool.name, describe(tool), output))
    raise GuideError("the guide did not give a plan")
