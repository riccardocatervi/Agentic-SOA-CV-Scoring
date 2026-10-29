"""A scripted LLM for tests: answers are written by hand, no model needed."""

import copy
import json
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from cvscore.llm.base import LLMResponse, Message, ToolCall


@dataclass
class ChatCall:
    """What the code under test sent to the model (kept for assertions)."""

    messages: list[Message]
    tools: list[dict[str, Any]] | None
    response_schema: type[BaseModel] | None
    max_tokens: int


def text(content: str) -> LLMResponse:
    return LLMResponse(content=content)


def structured(model: BaseModel) -> LLMResponse:
    return LLMResponse(content=model.model_dump_json())


def tool_call(name: str, arguments: dict[str, Any] | str, call_id: str = "call_1") -> LLMResponse:
    raw = arguments if isinstance(arguments, str) else json.dumps(arguments)
    return LLMResponse(tool_calls=[ToolCall(id=call_id, name=name, arguments=raw)])


class FakeLLMClient:
    """Returns the scripted responses in order. An Exception in the script is raised."""

    def __init__(self, script: Iterable[LLMResponse | Exception]):
        self._script = deque(script)
        self.calls: list[ChatCall] = []

    async def chat(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        response_schema: type[BaseModel] | None = None,
        max_tokens: int = 512,
    ) -> LLMResponse:
        self.calls.append(ChatCall(copy.deepcopy(messages), tools, response_schema, max_tokens))
        if not self._script:
            raise AssertionError("FakeLLMClient: script exhausted, unexpected extra call")
        item = self._script.popleft()
        if isinstance(item, Exception):
            raise item
        return item
