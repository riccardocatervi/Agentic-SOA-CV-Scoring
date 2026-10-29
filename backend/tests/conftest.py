import socket
import threading
import time

import pytest
import uvicorn

from cvscore.config import get_service_settings
from cvscore.mcp_server.server import mcp
from cvscore.mcp_server.services import cv_service, scoring_service, verify_service
from cvscore.schemas import (
    ParsedCv,
    ScoreResult,
    SearchHit,
    SearchResult,
    SectionInfo,
    VerifyResult,
)
from cvscore.storage import save_cv


@pytest.fixture
def store_cv(tmp_path, monkeypatch):
    """Save CV bytes into a temporary storage and return a function giving the cv_id."""
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    get_service_settings.cache_clear()  # settings are cached: force a re-read
    yield lambda data, filename: save_cv(data, filename)
    get_service_settings.cache_clear()


@pytest.fixture
def stub_services(monkeypatch):
    """Replace the services with canned answers, so gateway tests do not need real CV files."""

    def parse_cv(cv_id):
        return ParsedCv(cv_id=cv_id, n_chars=120, sections=[SectionInfo(name="Skills", n_chars=60)])

    def search_cv(cv_id, query, max_hits=5, context_chars=200):
        hit = SearchHit(section="Projects", text=f"... deployed with {query} ...")
        return SearchResult(cv_id=cv_id, query=query, hits=[hit])

    def verify_evidence(cv_id, quote, threshold=0.85):
        return VerifyResult(cv_id=cv_id, found="deployed" in quote, similarity=1.0)

    def compute_score(requirements, matches):
        return ScoreResult(
            score=len(matches),
            must_met=0,
            must_total=len(requirements),
            nice_met=0,
            nice_total=0,
            per_requirement=[],
        )

    monkeypatch.setattr(cv_service, "parse_cv", parse_cv)
    monkeypatch.setattr(cv_service, "search_cv", search_cv)
    monkeypatch.setattr(verify_service, "verify_evidence", verify_evidence)
    monkeypatch.setattr(scoring_service, "compute_score", compute_score)


@pytest.fixture(scope="session")
def live_gateway_url():
    """The real gateway served over HTTP on a free port, in a background thread."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    config = uvicorn.Config(
        mcp.streamable_http_app(host="127.0.0.1"),
        host="127.0.0.1",
        port=port,
        log_level="warning",
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while not server.started:
        if time.time() > deadline:
            raise RuntimeError("live gateway did not start")
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}/mcp"
    server.should_exit = True
    thread.join(timeout=5)
