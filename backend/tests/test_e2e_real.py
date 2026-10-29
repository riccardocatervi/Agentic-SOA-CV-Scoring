"""A whole job through the real gateway (HTTP) and the real services, with a scripted model.

Needs the services written by the CV/verify/scoring owner, so it is skipped until they exist.
"""

import pytest
from fakes import SAMPLE_JD, ScriptedAgentsLLM
from helpers import make_pdf

from cvscore.agents import run_job
from cvscore.mcp_client import Gateway
from cvscore.mcp_server.services import cv_service
from cvscore.mcp_server.services.errors import ServiceError
from cvscore.storage import StorageError


def _services_implemented() -> bool:
    try:
        cv_service.extract_text("0" * 32)
    except NotImplementedError:
        return False
    except (ServiceError, StorageError, ValueError):  # the real service ran: no such CV
        return True
    return True


pytestmark = pytest.mark.skipif(
    not _services_implemented(), reason="services are not implemented yet"
)

CV_LINES = [
    "JOHN DOE",
    "Backend developer",
    "EXPERIENCE",
    "Built a FastAPI service deployed with Docker Compose.",
    "Reduced latency by 40 percent using caching.",
    "SKILLS",
    "Python, SQL, Docker, pytest",
]


async def test_full_job_over_http_with_real_services(store_cv, live_gateway_url):
    cv_id = store_cv(make_pdf(CV_LINES), "cv.pdf")
    llm = ScriptedAgentsLLM()
    steps: list[str] = []

    async with Gateway(live_gateway_url) as gateway:
        result = await run_job(
            "e2e-1", cv_id, SAMPLE_JD, llm=llm, gateway=gateway, on_step=steps.append
        )

    by_id = {r.requirement_id: r for r in result.breakdown.per_requirement}
    assert result.score == 70
    assert by_id[3].verdict == "no"  # the invented Kubernetes quote was caught by the real verifier
    assert all(r.verified for r in result.breakdown.per_requirement)
    assert result.suggestions
