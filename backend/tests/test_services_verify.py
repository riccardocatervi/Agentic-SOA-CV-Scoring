import pytest
from helpers import SAMPLE_CV, make_docx, make_pdf

from cvscore.mcp_server.services import verify_service
from cvscore.storage import StorageError

pytestmark = pytest.mark.skip(reason="TODO(services owner): implement the services, then delete this line")


@pytest.fixture
def cv_id(store_cv):
    return store_cv(make_pdf(SAMPLE_CV), "cv.pdf")


def test_exact_quote_is_found(cv_id):
    result = verify_service.verify_evidence(cv_id, "Built a FastAPI service deployed with Docker")

    assert result.found
    assert result.similarity == 1.0


def test_case_and_spacing_do_not_matter(cv_id):
    result = verify_service.verify_evidence(cv_id, "built  a FASTAPI   service\ndeployed")
    assert result.found


def test_quote_split_across_lines_is_found(store_cv):
    cv_id = store_cv(make_docx(["Jane", "Led a team of five engi-", "neers on a data platform."]), "c.docx")

    result = verify_service.verify_evidence(cv_id, "team of five engineers")

    assert result.found


def test_curly_quotes_and_bullets_are_ignored(store_cv):
    cv_id = store_cv(make_docx(["Jane", "• Built the team's pipeline"]), "c.docx")

    result = verify_service.verify_evidence(cv_id, "Built the team’s pipeline")

    assert result.found


def test_small_typo_still_passes(cv_id):
    result = verify_service.verify_evidence(cv_id, "Reduced latency by 40% using cachng")

    assert result.found
    assert result.similarity < 1.0


def test_invented_claim_is_not_found(cv_id):
    quote = "Led a team of ten engineers migrating the platform to Kubernetes"

    assert not verify_service.verify_evidence(cv_id, quote).found


def test_very_short_quotes_are_never_accepted(cv_id):
    assert not verify_service.verify_evidence(cv_id, "a").found
    assert not verify_service.verify_evidence(cv_id, "  Pyth ").found


def test_threshold_is_respected(cv_id):
    quote = "Reduced latency by 40% using cachng"

    assert not verify_service.verify_evidence(cv_id, quote, threshold=0.999).found


def test_unknown_cv_id(store_cv):
    with pytest.raises(StorageError):
        verify_service.verify_evidence("0" * 32, "anything long enough")
