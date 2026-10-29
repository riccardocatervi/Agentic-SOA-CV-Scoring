"""Per-job state. It lives and dies with the job: nothing is shared between users (privacy)."""

from dataclasses import dataclass, field

from cvscore.llm.base import Usage
from cvscore.schemas import (
    AnalysisResult,
    Match,
    Requirement,
    VerifiedMatch,
)

MAX_MATCH_ATTEMPTS = 2


@dataclass
class JobMemory:
    job_id: str
    cv_id: str
    requirements: list[Requirement] = field(default_factory=list)
    matches: dict[int, Match] = field(default_factory=dict)
    verified: dict[int, VerifiedMatch] = field(default_factory=dict)
    attempts: dict[int, int] = field(default_factory=dict)
    result: AnalysisResult | None = None
    usage: Usage = field(default_factory=Usage)
    history: list[str] = field(default_factory=list)

    def requirement_ids(self) -> list[int]:
        return [r.id for r in self.requirements]

    def unmatched_ids(self) -> list[int]:
        return [i for i in self.requirement_ids() if i not in self.matches]

    def unchecked_ids(self) -> list[int]:
        """Matches whose quote has not been verified yet."""
        return [i for i in self.matches if i not in self.verified]

    def failed_ids(self) -> list[int]:
        """Verified matches whose quote was NOT found in the CV."""
        return [i for i, m in self.verified.items() if not m.verified]

    def retryable_ids(self) -> list[int]:
        return [i for i in self.failed_ids() if self.attempts.get(i, 0) < MAX_MATCH_ATTEMPTS]

    def record_matches(self, matches: list[Match]) -> None:
        for match in matches:
            self.matches[match.requirement_id] = match
            self.verified.pop(match.requirement_id, None)  # new answer: needs a new check
            self.attempts[match.requirement_id] = self.attempts.get(match.requirement_id, 0) + 1

    def note(self, line: str) -> None:
        self.history.append(line)
