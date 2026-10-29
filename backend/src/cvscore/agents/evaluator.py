"""Evaluator. Verification and scoring are deterministic (MCP tools driven by code);
only the written suggestions need the model."""

from collections.abc import Iterable

from cvscore.agents.loop import Outcome, Tools, load_prompt, run_structured
from cvscore.llm.base import LLMClient
from cvscore.schemas import (
    Match,
    Requirement,
    ScoreResult,
    Suggestion,
    SuggestionList,
    VerifiedMatch,
)

MAX_SUGGESTIONS = 5
MAX_QUOTE_CHARS = 1000  # the gateway rejects longer quotes


async def verify_matches(tools: Tools, cv_id: str, matches: Iterable[Match]) -> list[VerifiedMatch]:
    """Check every quote against the CV. A 'no' has no quote, so there is nothing to check."""
    verified: list[VerifiedMatch] = []
    for match in matches:
        if match.verdict == "no":
            ok = True
        else:
            quote = (match.evidence or "")[:MAX_QUOTE_CHARS]
            result = await tools.call("verify_evidence", {"cv_id": cv_id, "quote": quote})
            ok = bool(result.data and result.data.get("found")) and not result.is_error
        verified.append(VerifiedMatch(**match.model_dump(), verified=ok))
    return verified


async def compute_score(
    tools: Tools, requirements: list[Requirement], verified: list[VerifiedMatch]
) -> ScoreResult:
    result = await tools.call(
        "compute_score",
        {
            "requirements": [r.model_dump(mode="json") for r in requirements],
            "matches": [m.model_dump(mode="json") for m in verified],
        },
    )
    if result.is_error or result.data is None:
        raise RuntimeError(f"compute_score failed: {result.text}")
    return ScoreResult.model_validate(result.data)


def _outcome_label(row_verdict: str, verified: bool) -> str:
    if row_verdict != "no" and not verified:
        return "not verified (quote not found in the CV)"
    return {"yes": "met", "partial": "partial", "no": "not met"}[row_verdict]


async def write_suggestions(
    llm: LLMClient,
    requirements: list[Requirement],
    score: ScoreResult,
    *,
    max_tokens: int = 768,
) -> Outcome[list[Suggestion]]:
    by_id = {row.requirement_id: row for row in score.per_requirement}
    lines = []
    for req in requirements:
        row = by_id[req.id]
        label = _outcome_label(row.verdict, row.verified)
        lines.append(f"{req.id}. [{req.kind}] {req.text} -> {label}")
    user_message = f"Score: {score.score}/100.\nRequirements:\n" + "\n".join(lines)

    parsed, run = await run_structured(
        llm,
        SuggestionList,
        system_prompt=load_prompt("evaluator_advice"),
        user_message=user_message,
        tools=None,
        max_steps=1,
        max_tokens=max_tokens,
        label="evaluator",
    )
    known = {r.id for r in requirements}
    suggestions = [
        s for s in parsed.suggestions if s.requirement_id is None or s.requirement_id in known
    ]
    return Outcome(suggestions[:MAX_SUGGESTIONS], run.usage, run.steps)
