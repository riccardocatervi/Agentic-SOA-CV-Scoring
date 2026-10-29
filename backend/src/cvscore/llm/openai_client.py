"""LLMClient for any OpenAI-compatible server (local Ollama, the FBK box, OpenAI).

This is the only file in the project allowed to import `openai`. Everything else talks to
the `LLMClient` protocol in base.py, so swapping provider is a config change.
"""

from typing import Any

from openai import AsyncOpenAI
from pydantic import BaseModel

from cvscore.llm.base import LLMResponse, Message


class OpenAICompatibleClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = 60.0,
        max_retries: int = 3,
        backoff_base: float = 1.0,
        client: AsyncOpenAI | None = None,
    ):
        """Keep the settings and build the SDK client.

        Build it with max_retries=0: the SDK retries on its own and silently, and we want to
        count and log every retry. `client` is there so tests can inject a fake SDK.
        """
        raise NotImplementedError

    async def chat(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        response_schema: type[BaseModel] | None = None,
        max_tokens: int = 512,
    ) -> LLMResponse:
        """One call to /chat/completions, translated to our own types.

        - temperature 0, max_tokens as given.
        - tools go in as they are (already OpenAI-style).
        - response_schema -> response_format {"type": "json_schema", ...} built from
          schema.model_json_schema().
        - Map the answer to LLMResponse: content, tool_calls (id, name, raw arguments string),
          usage (0 if the server omits it), latency in seconds.
        - No choices in the answer -> raise LLMError.
        """
        raise NotImplementedError

    async def _create_with_retry(self, params: dict[str, Any]):
        """Call the SDK, retrying only what can get better by waiting.

        Retry on RateLimitError, APITimeoutError, APIConnectionError, InternalServerError, with
        exponential backoff and jitter: backoff_base * 2**attempt * random(0.5, 1.5). After
        max_retries retries raise LLMError. Any other OpenAIError (400, 401...) is our bug or a
        bad key: raise LLMError right away, retrying would only hide it.
        Log each retry with the attempt number and the reason, never the messages.
        """
        raise NotImplementedError
