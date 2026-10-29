"""Tool Gateway: the single entry point from the agents to the services.

Agents never import the services. They connect here over HTTP (MCP Streamable HTTP),
discover the tools with tools/list and run them with tools/call. This is also the
place for the cross-cutting concerns: input limits and call logging.
"""

import asyncio
import logging
import time
from collections.abc import Callable
from typing import Annotated, Any

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from cvscore.mcp_server.services import cv_service, scoring_service, verify_service
from cvscore.mcp_server.services.errors import ServiceError
from cvscore.schemas import (
    CvSection,
    ParsedCv,
    Requirement,
    ScoreResult,
    SearchResult,
    VerifiedMatch,
    VerifyResult,
)
from cvscore.storage import StorageError

log = logging.getLogger("cvscore.gateway")

mcp = MCPServer(
    "cvscore-gateway",
    instructions="Tools to read and check a candidate CV that was already uploaded. "
    "Every tool takes a cv_id: CV text is never passed around, only ids.",
)

CvId = Annotated[
    str, Field(pattern=r"^[0-9a-f]{32}$", description="Id of the uploaded CV (32 hex chars)")
]


async def _call(tool: str, cv_id: str | None, fn: Callable[..., Any], *args: Any, **kwargs: Any):
    """Run a (blocking) service in a worker thread, log the call, map expected errors.

    Services are plain sync functions that parse files: running them directly would
    block the event loop and freeze every other user. Logs carry the tool name, the
    opaque cv_id and the duration, never the CV content or the quote.
    """
    started = time.perf_counter()
    try:
        result = await asyncio.to_thread(fn, *args, **kwargs)
    except (ServiceError, StorageError, ValueError) as exc:
        elapsed_ms = (time.perf_counter() - started) * 1000
        log.info("tool=%s cv_id=%s status=error ms=%.0f", tool, cv_id, elapsed_ms)
        # ToolError messages reach the model; any other exception is hidden from it.
        raise ToolError(str(exc)) from exc
    elapsed_ms = (time.perf_counter() - started) * 1000
    log.info("tool=%s cv_id=%s status=ok ms=%.0f", tool, cv_id, elapsed_ms)
    return result


@mcp.tool()
async def parse_cv(cv_id: CvId) -> ParsedCv:
    """List the sections of the CV (name and size). Call it first to know where to look."""
    return await _call("parse_cv", cv_id, cv_service.parse_cv, cv_id)


@mcp.tool()
async def get_section(
    cv_id: CvId,
    name: Annotated[str, Field(min_length=1, max_length=80, description="Section name")],
    max_chars: Annotated[int, Field(ge=100, le=8000)] = 4000,
) -> CvSection:
    """Read the text of one CV section by name. Section names come from parse_cv."""
    return await _call("get_section", cv_id, cv_service.get_section, cv_id, name, max_chars)


@mcp.tool()
async def search_cv(
    cv_id: CvId,
    query: Annotated[str, Field(min_length=2, max_length=200, description="Word or phrase")],
    max_hits: Annotated[int, Field(ge=1, le=10)] = 5,
) -> SearchResult:
    """Search the CV for a word or phrase (case-insensitive).

    Returns short snippets, each with the section it comes from. An empty list means
    the CV does not contain that text: try a synonym, or conclude it is absent.
    """
    return await _call("search_cv", cv_id, cv_service.search_cv, cv_id, query, max_hits)


@mcp.tool()
async def verify_evidence(
    cv_id: CvId,
    quote: Annotated[str, Field(min_length=1, max_length=1000)],
) -> VerifyResult:
    """Check that a quote really appears in the CV (tolerates spacing and line breaks)."""
    return await _call("verify_evidence", cv_id, verify_service.verify_evidence, cv_id, quote)


@mcp.tool()
async def compute_score(
    requirements: Annotated[list[Requirement], Field(min_length=1, max_length=50)],
    matches: Annotated[list[VerifiedMatch], Field(max_length=50)],
) -> ScoreResult:
    """Compute the 0-100 score from the requirements and the verified matches."""
    return await _call(
        "compute_score", None, scoring_service.compute_score, requirements, matches
    )
