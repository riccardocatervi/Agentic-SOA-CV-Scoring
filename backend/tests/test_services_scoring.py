import pytest

from cvscore.mcp_server.services.scoring_service import compute_score
from cvscore.schemas import Requirement, VerifiedMatch

pytestmark = pytest.mark.skip(
    reason="TODO(services owner): implement the services, then delete this line"
)


def req(id, kind="must"):
    return Requirement(id=id, text=f"requirement {id}", kind=kind)


def match(id, verdict, verified=True):
    evidence = None if verdict == "no" else "some quote from the CV"
    return VerifiedMatch(requirement_id=id, verdict=verdict, evidence=evidence, verified=verified)


def test_everything_met_gives_100():
    result = compute_score([req(1), req(2, "nice")], [match(1, "yes"), match(2, "yes")])

    assert result.score == 100
    assert (result.must_met, result.must_total) == (1, 1)
    assert (result.nice_met, result.nice_total) == (1, 1)


def test_nothing_met_gives_0():
    result = compute_score([req(1), req(2)], [match(1, "no"), match(2, "no")])

    assert result.score == 0
    assert result.must_met == 0


def test_weights_and_partial_credit():
    # must yes (3), must partial (1.5), nice no (0) out of 3 + 3 + 1 = 7  ->  4.5 / 7 = 64.3
    requirements = [req(1), req(2), req(3, "nice")]
    matches = [match(1, "yes"), match(2, "partial"), match(3, "no")]

    result = compute_score(requirements, matches)

    assert result.score == 64
    assert result.must_met == 1  # the partial does not count as fully met
    assert [r.points for r in result.per_requirement] == [3.0, 1.5, 0.0]


def test_unverified_evidence_is_worth_nothing():
    result = compute_score([req(1)], [match(1, "yes", verified=False)])

    assert result.score == 0
    assert result.per_requirement[0].outcome == 0.0


def test_missing_match_counts_as_no():
    result = compute_score([req(1), req(2)], [match(1, "yes")])

    assert result.score == 50
    assert result.per_requirement[1].verdict == "no"


def test_rounding_is_half_up():
    # weights 3 + 3 + 1 + 1 = 8; only the first nice is met: 1 / 8 = 12.5 -> 13 (not 12)
    requirements = [req(1), req(2), req(3, "nice"), req(4, "nice")]
    matches = [match(3, "yes")]

    assert compute_score(requirements, matches).score == 13


def test_match_for_unknown_requirement_is_rejected():
    with pytest.raises(ValueError, match="unknown requirement 9"):
        compute_score([req(1)], [match(9, "yes")])


def test_duplicate_matches_are_rejected():
    with pytest.raises(ValueError, match="two matches"):
        compute_score([req(1)], [match(1, "yes"), match(1, "no")])
