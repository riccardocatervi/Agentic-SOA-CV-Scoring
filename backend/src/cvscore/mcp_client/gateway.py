"""Client side of the Tool Gateway. The only way agents reach the services."""

import json
from collections.abc import Collection
from contextlib import AsyncExitStack
from dataclasses import dataclass
from typing import Any, Self

from mcp import Client
from mcp.server import MCPServer

from cvscore.config import get_service_settings
from cvscore.mcp_client.errors import GatewayError


@dataclass(frozen=True)
class ToolResult:
    text: str  # what the model reads (compact JSON, or the error message)
    data: dict[str, Any] | None  # the same result, structured, for code
    is_error: bool


def _to_result(raw: Any) -> ToolResult:
    texts = [block.text for block in raw.content if getattr(block, "type", "") == "text"]
    data = raw.structured_content
    if raw.is_error:
        return ToolResult(text=" ".join(texts) or "tool error", data=None, is_error=True)
    if data is not None:
        return ToolResult(text=json.dumps(data, ensure_ascii=False), data=data, is_error=False)
    return ToolResult(text=" ".join(texts), data=None, is_error=False)


class Gateway:
    """One connection to the Tool Gateway. Use it with `async with`.

    target: URL of the gateway (default: MCP_GATEWAY_URL), or an MCPServer instance to
    connect in-process (tests only).
    """

    def __init__(self, target: str | MCPServer | None = None, timeout: float = 30.0):
        self._target = target or get_service_settings().mcp_gateway_url
        self._timeout = timeout
        self._stack = AsyncExitStack()
        self._client: Client | None = None

    async def __aenter__(self) -> Self:
        try:
            client = Client(self._target, read_timeout_seconds=self._timeout)
            self._client = await self._stack.enter_async_context(client)
        except Exception as exc:
            await self._stack.aclose()
            raise GatewayError(f"cannot connect to the tool gateway: {exc}") from exc
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self._stack.aclose()
        self._client = None

    def _connected(self) -> Client:
        if self._client is None:
            raise GatewayError("gateway is not connected: use `async with Gateway()`")
        return self._client

    async def list_tools(self) -> list[dict[str, Any]]:
        """Tools in OpenAI function format, as the LLM expects them."""
        try:
            listing = await self._connected().list_tools()
        except GatewayError:
            raise
        except Exception as exc:
            raise GatewayError(f"tools/list failed: {exc}") from exc
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description or "",
                    "parameters": tool.input_schema,
                },
            }
            for tool in listing.tools
        ]

    async def call(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        try:
            raw = await self._connected().call_tool(name, arguments)
        except GatewayError:
            raise
        except Exception as exc:
            raise GatewayError(f"tools/call {name} failed: {exc}") from exc
        return _to_result(raw)

    def toolbox(self, allowed: Collection[str]) -> "ToolBox":
        return ToolBox(self, allowed)


class ToolBox:
    """The tools one agent may use (least privilege). The allowlist lives in the registry."""

    def __init__(self, gateway: Gateway, allowed: Collection[str]):
        self._gateway = gateway
        self.allowed = frozenset(allowed)

    async def specs(self) -> list[dict[str, Any]]:
        all_tools = await self._gateway.list_tools()
        return [t for t in all_tools if t["function"]["name"] in self.allowed]

    async def call(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        if name not in self.allowed:
            # Asked by the model, so answer in a way it can learn from, do not raise.
            allowed = ", ".join(sorted(self.allowed)) or "none"
            return ToolResult(
                text=f"Unknown tool '{name}'. Available tools: {allowed}.",
                data=None,
                is_error=True,
            )
        return await self._gateway.call(name, arguments)
