from typing import Literal

from pydantic import BaseModel

from cvscore.schemas.result import AnalysisResult

JobStatus = Literal["queued", "processing", "done", "failed"]


class JobState(BaseModel):
    id: str
    status: JobStatus
    step: str | None = None
    result: AnalysisResult | None = None
    error: str | None = None
