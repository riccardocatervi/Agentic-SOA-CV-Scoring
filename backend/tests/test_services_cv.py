import pytest
from helpers import SAMPLE_CV, make_docx, make_pdf

from cvscore.mcp_server.services import cv_service
from cvscore.mcp_server.services.errors import ServiceError
from cvscore.storage import StorageError

pytestmark = pytest.mark.skip(
    reason="TODO(services owner): implement the services, then delete this line"
)


@pytest.fixture(params=["pdf", "docx"])
def cv_id(request, store_cv):
    if request.param == "pdf":
        return store_cv(make_pdf(SAMPLE_CV), "cv.pdf")
    return store_cv(make_docx(SAMPLE_CV), "cv.docx")


def test_parse_finds_the_sections(cv_id):
    parsed = cv_service.parse_cv(cv_id)

    names = [s.name for s in parsed.sections]
    assert names == ["Header", "EXPERIENCE", "EDUCATION", "SKILLS"]
    assert parsed.n_chars > 100
    assert all(s.n_chars > 0 for s in parsed.sections)


def test_first_line_is_the_name_not_a_heading(cv_id):
    header = cv_service.get_section(cv_id, "header")
    assert "JOHN DOE" in header.text


def test_get_section_ignores_case(cv_id):
    section = cv_service.get_section(cv_id, "skills")

    assert section.name == "SKILLS"
    assert "Docker" in section.text


def test_get_section_unknown_lists_the_valid_names(cv_id):
    with pytest.raises(ServiceError, match="EXPERIENCE"):
        cv_service.get_section(cv_id, "hobbies")


def test_get_section_is_truncated(cv_id):
    section = cv_service.get_section(cv_id, "experience", max_chars=20)
    assert len(section.text) == 20


def test_search_returns_snippet_and_section(cv_id):
    result = cv_service.search_cv(cv_id, "docker compose")

    assert result.hits[0].section == "EXPERIENCE"
    assert "Docker Compose" in result.hits[0].text


def test_search_without_matches_is_empty_not_an_error(cv_id):
    assert cv_service.search_cv(cv_id, "kubernetes").hits == []


def test_search_respects_max_hits(cv_id):
    result = cv_service.search_cv(cv_id, "a", max_hits=2, context_chars=4)
    assert len(result.hits) == 2


def test_cv_without_headings_is_one_section(store_cv):
    cv_id = store_cv(make_docx(["Jane", "I write Python code for a living."]), "cv.docx")

    parsed = cv_service.parse_cv(cv_id)

    assert [s.name for s in parsed.sections] == ["Full text"]


def test_scanned_pdf_has_no_text(store_cv):
    cv_id = store_cv(make_pdf([]), "scan.pdf")

    with pytest.raises(ServiceError, match="no extractable text"):
        cv_service.parse_cv(cv_id)


def test_corrupted_pdf_is_a_service_error(store_cv):
    cv_id = store_cv(b"%PDF-1.4 this is not really a pdf", "bad.pdf")

    with pytest.raises(ServiceError):
        cv_service.parse_cv(cv_id)


def test_corrupted_docx_is_a_service_error(store_cv):
    cv_id = store_cv(b"PK\x03\x04 not a real docx", "bad.docx")

    with pytest.raises(ServiceError):
        cv_service.parse_cv(cv_id)


def test_unknown_cv_id(store_cv):
    with pytest.raises(StorageError):
        cv_service.parse_cv("0" * 32)
