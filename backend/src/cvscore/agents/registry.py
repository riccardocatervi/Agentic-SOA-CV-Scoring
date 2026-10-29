"""The catalogue of sub-agents: what each one does and which tools it may touch.

Tools are discovered from the gateway (tools/list); this file only decides who may use what
(least privilege) and gives the orchestrator a description of its team.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentSpec:
    name: str
    description: str
    allowed_tools: frozenset[str]


REGISTRY: dict[str, AgentSpec] = {
    "jd_analyst": AgentSpec(
        name="jd_analyst",
        description="Reads the job description and extracts the list of requirements "
        "(each one 'must' or 'nice'). No tools. Run it once, first.",
        allowed_tools=frozenset(),
    ),
    "cv_matcher": AgentSpec(
        name="cv_matcher",
        description="Searches the CV for evidence of each requirement and answers yes / partial / "
        "no with a quote. Decides by itself where to look. Can be run again for specific "
        "requirement_ids when their quotes failed verification.",
        allowed_tools=frozenset({"parse_cv", "get_section", "search_cv"}),
    ),
    "evaluator": AgentSpec(
        name="evaluator",
        description="task 'verify': checks that every quote really exists in the CV. "
        "task 'report': computes the score and writes the suggestions (run it last).",
        allowed_tools=frozenset({"verify_evidence", "compute_score"}),
    ),
}


def describe() -> str:
    return "\n".join(f"- {spec.name}: {spec.description}" for spec in REGISTRY.values())
