"""CV parsing and text lookup. Pure functions, addressed by cv_id.

Find the file with cvscore.storage.get_cv_path(cv_id). Supports .pdf (pypdf) and
.docx (python-docx). Add both libraries with `uv add`.
"""

from cvscore.schemas import CvSection, ParsedCv, SearchResult


def extract_text(cv_id: str) -> str:
    """Return the full plain text of the CV.

    Raise ServiceError when the file is corrupted or has no extractable text
    (a scanned PDF is just images). Also cap the number of pages and characters
    so a huge file cannot eat the server.
    """
    raise NotImplementedError


def parse_cv(cv_id: str) -> ParsedCv:
    """Split the text into sections and describe them (names and sizes only).

    A section starts at a heading: a short line, alone, that is either upper case
    or one of the usual titles (experience, education, skills, projects, ...).
    Text before the first heading goes in a section called "Header". If no heading
    is found, return a single section called "Full text".
    """
    raise NotImplementedError


def get_section(cv_id: str, name: str, max_chars: int = 4000) -> CvSection:
    """Return the text of one section, truncated to max_chars.

    Match the name ignoring case. Raise ServiceError if it does not exist and list
    the section names that do, so the caller can retry.
    """
    raise NotImplementedError


def search_cv(
    cv_id: str, query: str, max_hits: int = 5, context_chars: int = 200
) -> SearchResult:
    """Find where the CV mentions the query.

    Case-insensitive. Each hit is a snippet of about context_chars around the match,
    with the name of the section it comes from. Return at most max_hits hits and
    an empty list (not an error) when nothing matches.
    """
    raise NotImplementedError
