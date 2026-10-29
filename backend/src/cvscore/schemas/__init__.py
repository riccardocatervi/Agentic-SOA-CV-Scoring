"""Shared data contracts. Changing anything here needs the agreement of all three of us."""

from cvscore.schemas.cv import (
    CvSection,
    ParsedCv,
    SearchHit,
    SearchResult,
    SectionInfo,
)
from cvscore.schemas.evidence import (
    Match,
    MatchList,
    Verdict,
    VerifiedMatch,
    VerifyResult,
)
from cvscore.schemas.jd import JobRequirements, Requirement
from cvscore.schemas.job import JobState, JobStatus
from cvscore.schemas.result import (
    AnalysisResult,
    RequirementScore,
    ScoreResult,
    Suggestion,
    SuggestionList,
)

__all__ = [
    "AnalysisResult",
    "CvSection",
    "JobRequirements",
    "JobState",
    "JobStatus",
    "Match",
    "MatchList",
    "ParsedCv",
    "Requirement",
    "RequirementScore",
    "ScoreResult",
    "SearchHit",
    "SearchResult",
    "SectionInfo",
    "Suggestion",
    "SuggestionList",
    "Verdict",
    "VerifiedMatch",
    "VerifyResult",
]
