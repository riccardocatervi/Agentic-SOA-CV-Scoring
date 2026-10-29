from typing import Literal

from pydantic import BaseModel, Field, model_validator

Verdict = Literal["yes", "partial", "no"]


class Match(BaseModel):
    """What the CV Matcher concludes for one requirement.

    A "yes" or "partial" must come with a quote from the CV. A "no" needs none:
    admitting that something is absent is a valid, honest outcome.
    """

    requirement_id: int
    verdict: Verdict
    evidence: str | None = None

    @model_validator(mode="after")
    def _evidence_required_unless_no(self) -> "Match":
        if self.verdict != "no" and not (self.evidence and self.evidence.strip()):
            raise ValueError("evidence is required when verdict is not 'no'")
        return self


class MatchList(BaseModel):
    """Structured output of the CV Matcher."""

    matches: list[Match]


class VerifiedMatch(Match):
    """A Match after verify_evidence. For verdict 'no' there is nothing to check: verified=True."""

    verified: bool


class VerifyResult(BaseModel):
    """Result of verify_evidence."""

    cv_id: str
    found: bool
    similarity: float = Field(ge=0.0, le=1.0)
