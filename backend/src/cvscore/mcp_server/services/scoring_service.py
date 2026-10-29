"""The score. Computed by code, never by the LLM."""

from cvscore.schemas import Requirement, ScoreResult, VerifiedMatch

MUST_WEIGHT = 3
NICE_WEIGHT = 1


def compute_score(requirements: list[Requirement], matches: list[VerifiedMatch]) -> ScoreResult:
    """score = round_half_up(100 * sum(weight * outcome) / sum(weight)).

    Weights: must = 3, nice = 1. Outcome: yes = 1, partial = 0.5, no = 0.
    A yes/partial that is not verified counts as 0: a quote we cannot find in the CV
    is worth nothing. A requirement with no match at all is treated as "no".
    must_met / nice_met count the verified "yes" only.
    Raise ValueError when a match points to an unknown requirement or when two
    matches point to the same one.
    """
    raise NotImplementedError
