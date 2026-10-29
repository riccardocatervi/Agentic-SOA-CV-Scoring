from pydantic import BaseModel


class SectionInfo(BaseModel):
    """A section of the CV, described without its text (text never travels in bulk)."""

    name: str
    n_chars: int


class ParsedCv(BaseModel):
    """Result of parse_cv: an overview of the document, not its content."""

    cv_id: str
    n_chars: int
    sections: list[SectionInfo]


class CvSection(BaseModel):
    """Result of get_section: the text of one section."""

    cv_id: str
    name: str
    text: str


class SearchHit(BaseModel):
    section: str
    text: str  # a short snippet around the match


class SearchResult(BaseModel):
    """Result of search_cv."""

    cv_id: str
    query: str
    hits: list[SearchHit]
