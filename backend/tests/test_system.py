"""The whole system, every layer real except the model itself.

POST /api/analyze -> queue -> orchestrator -> sub-agents -> OpenAI client --HTTP--> a tiny
server that speaks /v1/chat/completions (backed by the scripted model) and
sub-agents -> MCP client --HTTP--> gateway -> real services -> a real PDF.
"""

import asyncio
import socket
import threading
import time

import pytest
import uvicorn
from fakes import SAMPLE_JD, ScriptedAgentsLLM
from fastapi import FastAPI, Request
from helpers import make_pdf
from httpx import ASGITransport, AsyncClient

from cvscore.api import create_app
from cvscore.config import get_service_settings
from cvscore.jobs import JobManager, make_runner
from cvscore.llm.openai_client import OpenAICompatibleClient

CV_LINES = [
    "JOHN DOE",
    "EXPERIENCE",
    "Built a FastAPI service deployed with Docker Compose.",
    "SKILLS",
    "Python, SQL, Docker, pytest",
]


pytestmark = pytest.mark.skip(reason="needs the services, the LLM client, the queue and the API")


def build_fake_openai_server(model: ScriptedAgentsLLM) -> FastAPI:
    app = FastAPI()

    @app.post("/v1/chat/completions")
    async def completions(request: Request):
        body = await request.json()
        response = await model.chat(body["messages"], body.get("tools"))
        message = {"role": "assistant", "content": response.content}
        if response.tool_calls:
            message["tool_calls"] = [
                {
                    "id": c.id,
                    "type": "function",
                    "function": {"name": c.name, "arguments": c.arguments},
                }
                for c in response.tool_calls
            ]
        return {
            "id": "x",
            "object": "chat.completion",
            "created": 0,
            "model": body["model"],
            "choices": [{"index": 0, "message": message, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
        }

    return app


def serve(app) -> tuple[uvicorn.Server, str]:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    deadline = time.time() + 10
    while not server.started:
        assert time.time() < deadline, "server did not start"
        time.sleep(0.02)
    return server, f"http://127.0.0.1:{port}"


@pytest.fixture
def fake_llm_url():
    server, url = serve(build_fake_openai_server(ScriptedAgentsLLM()))
    yield url + "/v1"
    server.should_exit = True


async def test_many_users_at_once_through_the_whole_stack(
    store_cv, live_gateway_url, fake_llm_url, tmp_path
):
    llm = OpenAICompatibleClient(base_url=fake_llm_url, api_key="x", model="fake")
    manager = JobManager(
        make_runner(llm, gateway_url=live_gateway_url),
        k_consumers=4,
        storage_dir=get_service_settings().storage_dir,
    )
    app = create_app(manager)
    pdf = make_pdf(CV_LINES)
    users = 12

    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client,
    ):
        responses = await asyncio.gather(
            *[
                client.post(
                    "/api/analyze",
                    files={"cv": ("cv.pdf", pdf, "application/pdf")},
                    data={"jd_text": SAMPLE_JD},
                )
                for _ in range(users)
            ]
        )
        assert {r.status_code for r in responses} == {202}
        job_ids = [r.json()["job_id"] for r in responses]

        async with asyncio.timeout(30):
            bodies = []
            for job_id in job_ids:
                while (body := (await client.get(f"/api/jobs/{job_id}")).json())["status"] in (
                    "queued",
                    "processing",
                ):
                    await asyncio.sleep(0.05)
                bodies.append(body)

    assert [b["status"] for b in bodies] == ["done"] * users
    assert {b["result"]["score"] for b in bodies} == {70}
    leftovers = list((get_service_settings().storage_dir / "cv").glob("*"))
    assert leftovers == [], "CVs must be deleted after the job"
