"""The only LLM-facing contract in the project.

No other module imports `openai` or any provider SDK: they depend on `LLMClient`.
Messages use the OpenAI chat format (plain dicts), which Ollama also accepts.
"""

import re
from dataclasses import dataclass, field
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

Message = dict[str, Any]
T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    """Any failure talking to the model (timeout, 429/5xx after retries, bad payload)."""


class LLMOutputError(LLMError):
    """The model answered, but the answer does not match the expected schema."""


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: str  # raw JSON text, exactly as generated: the agent loop validates it


@dataclass(frozen=True)
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(
            self.prompt_tokens + other.prompt_tokens,
            self.completion_tokens + other.completion_tokens,
        )


_FENCE = re.compile(r"^```[a-zA-Z]*\s*(.*?)\s*```$", re.DOTALL)


def extract_json_text(text: str) -> str:
    """Models often wrap JSON in a code fence or add a sentence around it: peel that off."""
    text = text.strip()
    fenced = _FENCE.match(text)
    if fenced:
        text = fenced.group(1)
    if not text.startswith(("{", "[")):
        starts = [i for i in (text.find("{"), text.find("[")) if i != -1]
        end = max(text.rfind("}"), text.rfind("]"))
        if starts and end > min(starts):
            text = text[min(starts) : end + 1]
    return text


@dataclass(frozen=True)
class LLMResponse:
    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    latency_s: float = 0.0

    def to_message(self) -> Message:
        """The assistant message to append to the conversation before tool results."""
        message: Message = {"role": "assistant", "content": self.content}
        if self.tool_calls:
            message["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {"name": call.name, "arguments": call.arguments},
                }
                for call in self.tool_calls
            ]
        return message

    def parse(self, schema: type[T]) -> T:
        """Validate the text content against a Pydantic model."""
        if not self.content:
            raise LLMOutputError("empty response, expected JSON")
        try:
            return schema.model_validate_json(extract_json_text(self.content))
        except ValidationError as exc:
            raise LLMOutputError(f"response does not match {schema.__name__}: {exc}") from exc


class LLMClient(Protocol):
    async def chat(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        response_schema: type[BaseModel] | None = None,
        max_tokens: int = 512,
    ) -> LLMResponse:
        """One model call.

        tools: OpenAI-style function schemas. response_schema: ask for JSON matching it.
        Raises LLMError on failure.
        """
        ...
