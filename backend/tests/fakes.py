"""Test doubles for the agent layer: a gateway that needs no services, and a rule-based LLM."""

import json
import re
from collections.abc import Collection
from typing import Any

from pydantic import BaseModel

from cvscore.llm.base import LLMResponse, Message, ToolCall
from cvscore.mcp_client import ToolResult

SAMPLE_JD = """We are hiring a backend engineer for our data platform.
Requirements:
- Python
- Docker
- Kubernetes
Nice to have:
- pytest
"""

SAMPLE_CV_TEXT = (
    "JOHN DOE Backend developer. "
    "Built a FastAPI service deployed with Docker Compose. "
    "Reduced latency by 40% using caching. "
    "Skills: Python, SQL, Docker, pytest"
)


def _spec(name: str, properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    schema = {"type": "object", "properties": properties, "required": required}
    return {
        "type": "function",
        "function": {"name": name, "description": name, "parameters": schema},
    }


FAKE_TOOL_SPECS = [
    _spec("parse_cv", {"cv_id": {"type": "string"}}, ["cv_id"]),
    _spec("get_section", {"cv_id": {"type": "string"}, "name": {"type": "string"}}, ["cv_id", "name"]),
    _spec("search_cv", {"cv_id": {"type": "string"}, "query": {"type": "string"}}, ["cv_id", "query"]),
    _spec("verify_evidence", {"cv_id": {"type": "string"}, "quote": {"type": "string"}}, ["cv_id", "quote"]),
    _spec("compute_score", {"requirements": {"type": "array"}, "matches": {"type": "array"}}, ["requirements", "matches"]),
]  # fmt: skip


def _ok(data: dict[str, Any]) -> ToolResult:
    return ToolResult(text=json.dumps(data), data=data, is_error=False)


class FakeToolBox:
    done = False

    def __init__(self, cv_text: str, allowed: Collection[str]):
        self._cv_text = cv_text
        self.allowed = frozenset(allowed)
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def specs(self) -> list[dict[str, Any]]:
        return [s for s in FAKE_TOOL_SPECS if s["function"]["name"] in self.allowed]

    async def call(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        self.calls.append((name, arguments))
        if name not in self.allowed:
            return ToolResult(text=f"Unknown tool '{name}'", data=None, is_error=True)
        if name == "search_cv":
            query = arguments["query"].lower()
            index = self._cv_text.lower().find(query)
            hits = []
            if index != -1:
                snippet = self._cv_text[max(0, index - 40) : index + len(query) + 40]
                hits = [{"section": "Body", "text": snippet}]
            return _ok({"cv_id": arguments["cv_id"], "query": arguments["query"], "hits": hits})
        if name == "verify_evidence":
            found = " ".join(arguments["quote"].lower().split()) in " ".join(
                self._cv_text.lower().split()
            )
            return _ok(
                {"cv_id": arguments["cv_id"], "found": found, "similarity": 1.0 if found else 0.2}
            )
        if name == "compute_score":
            return _ok(_fake_score(arguments["requirements"], arguments["matches"]))
        return _ok({})


def _fake_score(requirements: list[dict], matches: list[dict]) -> dict[str, Any]:
    """Same formula as the real service, kept tiny: the tests below do not test the formula."""
    by_id = {m["requirement_id"]: m for m in matches}
    rows, earned, total = [], 0.0, 0
    for req in requirements:
        weight = 3 if req["kind"] == "must" else 1
        match = by_id.get(req["id"], {"verdict": "no", "verified": True})
        outcome = {"yes": 1.0, "partial": 0.5, "no": 0.0}[match["verdict"]] * match["verified"]
        rows.append(
            {
                "requirement_id": req["id"], "kind": req["kind"], "verdict": match["verdict"],
                "verified": match["verified"], "weight": weight, "outcome": outcome,
                "points": weight * outcome,
            }
        )  # fmt: skip
        earned += weight * outcome
        total += weight
    full = [r for r in rows if r["outcome"] == 1.0]
    return {
        "score": int(100 * earned / total + 0.5),
        "must_met": sum(1 for r in full if r["kind"] == "must"),
        "must_total": sum(1 for r in rows if r["kind"] == "must"),
        "nice_met": sum(1 for r in full if r["kind"] == "nice"),
        "nice_total": sum(1 for r in rows if r["kind"] == "nice"),
        "per_requirement": rows,
    }


class FakeGateway:
    """Quacks like cvscore.mcp_client.Gateway, but answers from a CV text held in memory."""

    def __init__(self, cv_text: str = SAMPLE_CV_TEXT):
        self.cv_text = cv_text
        self.toolboxes: list[FakeToolBox] = []

    def toolbox(self, allowed: Collection[str]) -> FakeToolBox:
        box = FakeToolBox(self.cv_text, allowed)
        self.toolboxes.append(box)
        return box


# --- A rule-based "model" that plays all four agents, so whole jobs can run in tests ----------


def _json(model: BaseModel | dict) -> LLMResponse:
    payload = model.model_dump_json() if isinstance(model, BaseModel) else json.dumps(model)
    return LLMResponse(content=payload)


def _tool_calls(*calls: tuple[str, dict]) -> LLMResponse:
    return LLMResponse(
        tool_calls=[
            ToolCall(id=f"call_{i}", name=name, arguments=json.dumps(args))
            for i, (name, args) in enumerate(calls)
        ]
    )


class ScriptedAgentsLLM:
    """Decides like a reasonable model would, from the system prompt and the conversation.

    It also lies once on purpose: the first time it is asked about Kubernetes it invents a quote,
    so the verification and the targeted retry get exercised.
    """

    def __init__(self) -> None:
        self.calls_by_agent: dict[str, int] = {}

    async def chat(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        response_schema: type[BaseModel] | None = None,
        max_tokens: int = 512,
    ) -> LLMResponse:
        system = messages[0]["content"]
        agent = next(
            (n for n in ("JD Analyst", "CV Matcher", "Evaluator", "Orchestrator") if f"You are the {n}" in system),
            "unknown",
        )  # fmt: skip
        self.calls_by_agent[agent] = self.calls_by_agent.get(agent, 0) + 1
        return await getattr(self, f"_{agent.lower().replace(' ', '_')}")(messages)

    async def _jd_analyst(self, messages: list[Message]) -> LLMResponse:
        jd = messages[1]["content"]
        nice = False
        items = []
        for line in jd.splitlines():
            if line.lower().startswith("nice to have"):
                nice = True
            elif line.startswith("- "):
                items.append(
                    {
                        "id": len(items) + 1,
                        "text": line[2:].strip(),
                        "kind": "nice" if nice else "must",
                    }
                )
        return _json({"requirements": items})  # fmt: skip

    async def _cv_matcher(self, messages: list[Message]) -> LLMResponse:
        user = messages[1]["content"]
        requirements = re.findall(r"^(\d+)\. \[(must|nice)\] (.+)$", user, re.MULTILINE)
        cv_id = re.search(r"cv_id: (\S+)", user).group(1)
        tool_messages = [m for m in messages if m["role"] == "tool"]
        if not tool_messages:
            return _tool_calls(
                *[("search_cv", {"cv_id": cv_id, "query": text}) for _, _, text in requirements]
            )
        hits_by_query = {}
        for message in tool_messages:
            data = json.loads(message["content"])
            hits_by_query[data["query"].lower()] = data["hits"]
        retrying = "NOT found" in user
        matches = []
        for rid, _, text in requirements:
            hits = hits_by_query.get(text.lower(), [])
            if "kubernetes" in text.lower() and not retrying:
                matches.append({"requirement_id": int(rid), "verdict": "yes",
                                "evidence": "Managed production Kubernetes clusters for three years"})  # fmt: skip
            elif hits:
                matches.append(
                    {"requirement_id": int(rid), "verdict": "yes", "evidence": hits[0]["text"]}
                )
            else:
                matches.append({"requirement_id": int(rid), "verdict": "no", "evidence": None})
        return _json({"matches": matches})

    async def _evaluator(self, messages: list[Message]) -> LLMResponse:
        rows = re.findall(
            r"^(\d+)\. \[(?:must|nice)\] (.+) -> (.+)$", messages[1]["content"], re.MULTILINE
        )
        suggestions = [
            {"requirement_id": int(rid), "text": f"If you have used {text}, mention where and how."}
            for rid, text, outcome in rows
            if outcome != "met"
        ]
        return _json({"suggestions": suggestions})

    async def _orchestrator(self, messages: list[Message]) -> LLMResponse:
        results = [m["content"] for m in messages if m["role"] == "tool"]
        last = results[-1] if results else ""
        if not results:
            return _tool_calls(("delegate", {"agent": "jd_analyst"}))
        if "requirements extracted" in last:
            return _tool_calls(("delegate", {"agent": "cv_matcher"}))
        if last.startswith("matched"):
            return _tool_calls(("delegate", {"agent": "evaluator", "task": "verify"}))
        if "all quotes found" in last or "No retries left" in last:
            return _tool_calls(("delegate", {"agent": "evaluator", "task": "report"}))
        if retry := re.search(r"can retry \[(.*?)\]", last):
            ids = [int(i) for i in retry.group(1).split(",")]
            return _tool_calls(("delegate", {"agent": "cv_matcher", "requirement_ids": ids}))
        if last.startswith("score"):
            return _tool_calls(("finish", {}))
        return LLMResponse(content="I do not know what to do next.")
