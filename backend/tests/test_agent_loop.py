import json
from typing import Any

import pytest
from pydantic import BaseModel

from cvscore.agents.loop import (
    MAX_TOOL_RESULT_CHARS,
    AgentOutputError,
    StepLimitExceeded,
    execute_tool_call,
    run_loop,
    run_structured,
)
from cvscore.llm import FakeLLMClient
from cvscore.llm.fake import text, tool_call
from cvscore.mcp_client import ToolResult


class FakeTools:
    """Two behaviours: `echo` returns its argument, `big` returns a huge text."""

    def __init__(self, stop_after: str | None = None):
        self.done = False
        self.calls: list[tuple[str, dict]] = []
        self._stop_after = stop_after

    async def specs(self) -> list[dict[str, Any]]:
        return [{"type": "function", "function": {"name": "echo", "parameters": {}}}]

    async def call(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        self.calls.append((name, arguments))
        if name == "big":
            return ToolResult(text="x" * (MAX_TOOL_RESULT_CHARS * 2), data=None, is_error=False)
        if name == self._stop_after:
            self.done = True
        return ToolResult(text=f"echo:{arguments.get('value')}", data=None, is_error=False)


class Answer(BaseModel):
    value: int


async def loop(llm, tools=None, **kwargs):
    return await run_loop(llm, system_prompt="sys", user_message="go", tools=tools, **kwargs)


async def test_answers_without_tools_in_one_step():
    llm = FakeLLMClient([text("hello")])

    run = await loop(llm)

    assert run.final.content == "hello"
    assert (run.steps, run.tool_calls) == (1, 0)


async def test_runs_the_tool_and_sends_the_result_back():
    tools = FakeTools()
    llm = FakeLLMClient([tool_call("echo", {"value": 7}, "c1"), text("done")])

    run = await loop(llm, tools)

    assert tools.calls == [("echo", {"value": 7})]
    second_call = llm.calls[1].messages
    assert second_call[-1] == {"role": "tool", "tool_call_id": "c1", "content": "echo:7"}
    assert (
        second_call[-2]["tool_calls"][0]["id"] == "c1"
    )  # the request is replayed before the result
    assert (run.steps, run.tool_calls) == (2, 1)


async def test_the_model_sees_the_tool_specs():
    tools = FakeTools()
    llm = FakeLLMClient([text("ok")])

    await loop(llm, tools)

    assert llm.calls[0].tools[0]["function"]["name"] == "echo"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("{not json", "not valid JSON"),
        ('["a list"]', "must be a JSON object"),
    ],
)
async def test_bad_arguments_become_a_message_not_a_crash(raw, expected):
    result = await execute_tool_call("echo", raw, FakeTools())

    assert result.is_error
    assert expected in result.text


async def test_loop_survives_bad_arguments_and_lets_the_model_retry():
    tools = FakeTools()
    llm = FakeLLMClient(
        [tool_call("echo", "{oops"), tool_call("echo", {"value": 1}), text("fixed")]
    )

    run = await loop(llm, tools)

    assert tools.calls == [("echo", {"value": 1})]  # only the valid call reached the tool
    assert run.final.content == "fixed"
    assert llm.calls[1].messages[-1]["content"].startswith("ERROR")


async def test_tool_call_without_any_tools_is_answered_with_an_error():
    llm = FakeLLMClient([tool_call("echo", {}), text("ok")])

    await loop(llm, tools=None)

    assert "no tools" in llm.calls[1].messages[-1]["content"]


async def test_huge_tool_results_are_truncated():
    llm = FakeLLMClient([tool_call("big", {}), text("ok")])

    await loop(llm, FakeTools())

    content = llm.calls[1].messages[-1]["content"]
    assert len(content) < MAX_TOOL_RESULT_CHARS + 50
    assert content.endswith("[truncated]")


async def test_done_flag_stops_the_loop_without_another_model_call():
    tools = FakeTools(stop_after="echo")
    llm = FakeLLMClient([tool_call("echo", {})])  # a second call would exhaust the script

    run = await loop(llm, tools)

    assert run.steps == 1
    assert len(llm.calls) == 1


async def test_last_step_takes_the_tools_away_and_asks_for_an_answer():
    llm = FakeLLMClient([tool_call("echo", {}), tool_call("echo", {}), text("best effort")])

    run = await loop(llm, FakeTools(), max_steps=3)

    assert run.final.content == "best effort"
    assert llm.calls[0].tools and llm.calls[1].tools
    assert llm.calls[2].tools is None
    assert "no tool calls left" in llm.calls[2].messages[-1]["content"]


async def test_step_limit_is_enforced_when_the_model_insists():
    llm = FakeLLMClient([tool_call("echo", {})] * 3)

    with pytest.raises(StepLimitExceeded):
        await loop(llm, FakeTools(), max_steps=3)

    assert len(llm.calls) == 3  # it stopped by itself, it did not run forever


async def test_usage_is_summed_over_the_steps():
    from cvscore.llm import LLMResponse, Usage

    first = tool_call("echo", {})
    first = LLMResponse(tool_calls=first.tool_calls, usage=Usage(100, 10))
    llm = FakeLLMClient([first, LLMResponse(content="ok", usage=Usage(150, 5))])

    run = await loop(llm, FakeTools())

    assert run.usage == Usage(250, 15)


async def test_structured_output_is_validated():
    llm = FakeLLMClient([text(json.dumps({"value": 3}))])

    value, _ = await run_structured(llm, Answer, system_prompt="s", user_message="u")

    assert value == Answer(value=3)
    assert llm.calls[0].response_schema is Answer  # no tools offered, so the schema is requested


async def test_malformed_answer_is_repaired_once():
    llm = FakeLLMClient([text("sure, the value is three"), text('{"value": 3}')])

    value, run = await run_structured(llm, Answer, system_prompt="s", user_message="u")

    assert value == Answer(value=3)
    assert "ONLY the JSON" in llm.calls[1].messages[-1]["content"]
    assert run.steps == 2


async def test_answer_that_stays_malformed_fails_clearly():
    llm = FakeLLMClient([text("nope"), text("still nope")])

    with pytest.raises(AgentOutputError):
        await run_structured(llm, Answer, system_prompt="s", user_message="u", label="tester")
