from typing import Literal

from pydantic import BaseModel, Field

from cvscore.schemas.evidence import Verdict


class RequirementScore(BaseModel):
    """How one requirement contributed to the score."""

    requirement_id: int
    kind: Literal["must", "nice"]
    verdict: Verdict
    verified: bool
    weight: int  # must=3, nice=1
    outcome: float = Field(ge=0.0, le=1.0)  # yes=1, partial=0.5, no=0; unverified counts as 0
    points: float  # weight * outcome


class ScoreResult(BaseModel):
    """Result of compute_score. "met" means fully met: a verified "yes"."""

    score: int = Field(ge=0, le=100)
    must_met: int
    must_total: int
    nice_met: int
    nice_total: int
    per_requirement: list[RequirementScore]


class Suggestion(BaseModel):
    requirement_id: int | None = None
    text: str = Field(min_length=1)


class SuggestionList(BaseModel):
    """Structured output of the Evaluator's advice step."""

    suggestions: list[Suggestion]


class AnalysisResult(BaseModel):
    """The final answer of a job."""

    score: int = Field(ge=0, le=100)
    breakdown: ScoreResult
    suggestions: list[Suggestion]
