"""CV Matcher: the agent with real autonomy. It decides what to search and when to stop."""

from cvscore.agents.loop import Outcome, Tools, load_prompt, run_structured
from cvscore.llm.base import LLMClient
from cvscore.schemas import Match, MatchList, Requirement


async def match_requirements(
    llm: LLMClient,
    tools: Tools,
    cv_id: str,
    requirements: list[Requirement],
    *,
    feedback: str | None = None,
    max_steps: int = 10,
    max_tokens: int = 1024,
) -> Outcome[list[Match]]:
    lines = [f"{r.id}. [{r.kind}] {r.text}" for r in requirements]
    user_message = f"cv_id: {cv_id}\nRequirements to check:\n" + "\n".join(lines)
    if feedback:
        user_message += f"\n\nNote from the orchestrator: {feedback}"

    parsed, run = await run_structured(
        llm,
        MatchList,
        system_prompt=load_prompt("cv_matcher"),
        user_message=user_message,
        tools=tools,
        max_steps=max_steps,
        max_tokens=max_tokens,
        label="cv_matcher",
    )

    # Keep only what was asked, once per requirement: the model can repeat or invent ids.
    asked = {r.id for r in requirements}
    seen: set[int] = set()
    matches: list[Match] = []
    for match in parsed.matches:
        if match.requirement_id in asked and match.requirement_id not in seen:
            seen.add(match.requirement_id)
            matches.append(match)
    return Outcome(matches, run.usage, run.steps)
