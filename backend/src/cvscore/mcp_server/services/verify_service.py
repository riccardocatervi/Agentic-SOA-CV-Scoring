"""Anti-hallucination check: does a quote really appear in the CV?"""

from cvscore.schemas import VerifyResult


def normalize(text: str) -> str:
    """Make two texts comparable.

    Unicode NFKC, lower case, join words broken by a hyphen at the end of a line,
    collapse every run of whitespace into one space. PDF extraction produces odd
    line breaks and hyphens, and these break naive matching.
    """
    raise NotImplementedError


def verify_evidence(cv_id: str, quote: str, threshold: float = 0.85) -> VerifyResult:
    """Check that `quote` is in the CV text.

    Exact match after normalize() gives similarity 1.0. Otherwise slide a window of
    the same length over the text and keep the best fuzzy ratio (difflib is enough).
    found is True when similarity >= threshold.
    Quotes shorter than 6 characters after normalization are never accepted: one
    common word would "verify" anything. Raise ServiceError for an unknown cv_id.
    """
    raise NotImplementedError
