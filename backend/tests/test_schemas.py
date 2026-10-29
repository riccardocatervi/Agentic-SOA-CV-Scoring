import pytest
from pydantic import ValidationError

from cvscore.schemas import (
    JobRequirements,
    JobState,
    Match,
    MatchList,
    Requirement,
    ScoreResult,
    VerifiedMatch,
)


def test_requirement_rejects_unknown_kind():
    with pytest.raises(ValidationError):
        Requirement(id=1, text="Docker", kind="optional")


def test_requirement_rejects_empty_text():
    with pytest.raises(ValidationError):
        Requirement(id=1, text="", kind="must")


def test_job_requirements_needs_at_least_one():
    with pytest.raises(ValidationError):
        JobRequirements(requirements=[])


def test_job_requirements_ids_must_be_unique():
    reqs = [
        Requirement(id=1, text="Python", kind="must"),
        Requirement(id=1, text="Docker", kind="nice"),
    ]
    with pytest.raises(ValidationError):
        JobRequirements(requirements=reqs)


@pytest.mark.parametrize("verdict", ["yes", "partial"])
def test_match_requires_evidence_unless_no(verdict):
    with pytest.raises(ValidationError):
        Match(requirement_id=1, verdict=verdict)
    with pytest.raises(ValidationError):
        Match(requirement_id=1, verdict=verdict, evidence="   ")


def test_match_no_does_not_need_evidence():
    match = Match(requirement_id=1, verdict="no")
    assert match.evidence is None


def test_match_with_evidence_is_valid():
    match = Match(requirement_id=2, verdict="yes", evidence="Deployed with Docker Compose")
    assert match.verdict == "yes"


def test_verified_match_inherits_the_evidence_rule():
    with pytest.raises(ValidationError):
        VerifiedMatch(requirement_id=1, verdict="yes", verified=True)


def test_match_list_round_trips_through_json():
    original = MatchList(matches=[Match(requirement_id=1, verdict="no")])
    assert MatchList.model_validate_json(original.model_dump_json()) == original


def test_score_must_be_between_0_and_100():
    with pytest.raises(ValidationError):
        ScoreResult(
            score=101, must_met=0, must_total=0, nice_met=0, nice_total=0, per_requirement=[]
        )


def test_job_state_rejects_unknown_status():
    with pytest.raises(ValidationError):
        JobState(id="abc", status="running")
