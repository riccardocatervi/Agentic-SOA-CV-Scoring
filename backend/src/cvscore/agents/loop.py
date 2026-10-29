"""The generic agent loop: the model asks for tools, we run them, repeat until it answers.

Written by hand on purpose (no framework): the "memory" of the agent is just the list of
messages, and it grows at every step. The loop always has a ceiling on the number of steps.
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel

from cvscore.llm.base import LLMClient, LLMOutputError, LLMResponse, Message, Usage
from cvscore.mcp_client import ToolResult

log = logging.getLogger("cvscore.agent")

MAX_TOOL_RESULT_CHARS = 4000
OUT_OF_STEPS_NUDGE = (
    "You have no tool calls left. Give your final answer now, using only what you found so far."
)
_PROMPTS_DIR = Path(__file__).parent / "prompts"


class StepLimitExceeded(Exception):
    """The agent still wanted to call tools after its last allowed step."""


class AgentOutputError(Exception):
    """The agent never produced an answer matching the expected schema."""


class Tools(Protocol):
    """What the loop needs from a set of tools. `ToolBox` (MCP) is one; the orchestrator has its own."""

    done: bool  # a tool can set it to stop the loop without another model call

    async def specs(self) -> list[dict[str, Any]]: ...

    async def call(self, name: str, arguments: dict[str, Any]) -> ToolResult: ...


@dataclass
class AgentRun:
    messages: list[Message]
    final: LLMResponse
    steps: int = 0
    tool_calls: int = 0
    usage: Usage = field(default_factory=Usage)


@dataclass
class Outcome[T]:
    """What a sub-agent hands back: the validated value plus what it cost."""

    value: T
    usage: Usage
    steps: int


def load_prompt(name: str) -> str:
    return (_PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8").strip()


def _tool_error(message: str) -> ToolResult:
    return ToolResult(text=f"ERROR: {message}", data=None, is_error=True)


async def execute_tool_call(name: str, raw_arguments: str, tools: Tools | None) -> ToolResult:
    """Run one tool call. Whatever the model got wrong becomes a message it can read and fix."""
    if tools is None:
        return _tool_error("no tools are available")
    try:
        arguments = json.loads(raw_arguments or "{}")
    except json.JSONDecodeError as exc:
        return _tool_error(f"arguments are not valid JSON ({exc.msg}). Send a JSON object.")
    if not isinstance(arguments, dict):
        return _tool_error("arguments must be a JSON object")
    result = await tools.call(name, arguments)
    if len(result.text) > MAX_TOOL_RESULT_CHARS:
        text = result.text[:MAX_TOOL_RESULT_CHARS] + " ...[truncated]"
        result = ToolResult(text=text, data=result.data, is_error=result.is_error)
    return result


async def run_loop(
    llm: LLMClient,
    *,
    system_prompt: str,
    user_message: str,
    tools: Tools | None = None,
    response_schema: type[BaseModel] | None = None,
    max_steps: int = 10,
    max_tokens: int = 512,
    label: str = "agent",
) -> AgentRun:
    messages: list[Message] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    specs = await tools.specs() if tools is not None else []
    usage = Usage()
    tool_calls = 0

    for step in range(1, max_steps + 1):
        last_step = step == max_steps
        offered = specs if specs and not last_step else None
        if last_step and specs:
            messages.append({"role": "user", "content": OUT_OF_STEPS_NUDGE})
        # JSON mode and tools do not always mix: constrain the output only when no tool is offered.
        schema = response_schema if offered is None else None
        response = await llm.chat(messages, offered, schema, max_tokens)
        usage = usage + response.usage
        messages.append(response.to_message())

        if not response.tool_calls:
            return AgentRun(messages, response, step, tool_calls, usage)
        if last_step:
            break

        for call in response.tool_calls:
            tool_calls += 1
            result = await execute_tool_call(call.name, call.arguments, tools)
            log.info(
                "agent=%s step=%d tool=%s status=%s",
                label, step, call.name, "error" if result.is_error else "ok",
            )  # fmt: skip
            messages.append({"role": "tool", "tool_call_id": call.id, "content": result.text})
        if tools is not None and tools.done:
            return AgentRun(messages, response, step, tool_calls, usage)

    raise StepLimitExceeded(f"{label} used all {max_steps} steps and still wanted tools")


async def run_structured[T: BaseModel](
    llm: LLMClient,
    schema: type[T],
    *,
    repair_attempts: int = 1,
    max_tokens: int = 512,
    **kwargs: Any,
) -> tuple[T, AgentRun]:
    """run_loop, then validate the final answer. If it is malformed, ask the model to fix it."""
    run = await run_loop(llm, response_schema=schema, max_tokens=max_tokens, **kwargs)
    label = kwargs.get("label", "agent")
    for attempt in range(repair_attempts + 1):
        try:
            return run.final.parse(schema), run
        except LLMOutputError as exc:
            if attempt == repair_attempts:
                raise AgentOutputError(f"{label}: invalid answer after repair: {exc}") from exc
            log.info("agent=%s repair attempt=%d", label, attempt + 1)
            run.messages.append(
                {
                    "role": "user",
                    "content": "Your answer is not valid JSON for the requested format "
                    f"({str(exc)[:300]}). Reply again with ONLY the JSON object.",
                }
            )
            response = await llm.chat(run.messages, None, schema, max_tokens)
            run.messages.append(response.to_message())
            run.final = response
            run.usage = run.usage + response.usage
            run.steps += 1
    raise AssertionError("unreachable")  # the loop always returns or raises
