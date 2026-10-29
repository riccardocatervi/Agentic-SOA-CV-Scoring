from typing import Literal

from pydantic import BaseModel, Field, model_validator


class Requirement(BaseModel):
    id: int
    text: str = Field(min_length=1)
    kind: Literal["must", "nice"]


class JobRequirements(BaseModel):
    """Structured output of the JD Analyst: the only thing that leaves the job description."""

    requirements: list[Requirement] = Field(min_length=1)

    @model_validator(mode="after")
    def _ids_are_unique(self) -> "JobRequirements":
        ids = [r.id for r in self.requirements]
        if len(ids) != len(set(ids)):
            raise ValueError("requirement ids must be unique")
        return self
