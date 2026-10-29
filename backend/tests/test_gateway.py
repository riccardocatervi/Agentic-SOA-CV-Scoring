import pytest

from cvscore.mcp_client import Gateway, GatewayError
from cvscore.mcp_server.server import mcp
from cvscore.mcp_server.services import cv_service
from cvscore.mcp_server.services.errors import ServiceError

CV_ID = "a" * 32


async def test_lists_the_five_tools_in_openai_format(stub_services):
    async with Gateway(mcp) as gateway:
        tools = await gateway.list_tools()

    names = {t["function"]["name"] for t in tools}
    assert names == {"parse_cv", "get_section", "search_cv", "verify_evidence", "compute_score"}
    search = next(t for t in tools if t["function"]["name"] == "search_cv")
    assert search["type"] == "function"
    assert search["function"]["description"]
    assert set(search["function"]["parameters"]["required"]) == {"cv_id", "query"}


async def test_call_returns_text_and_structured_data(stub_services):
    async with Gateway(mcp) as gateway:
        result = await gateway.call("search_cv", {"cv_id": CV_ID, "query": "Docker"})

    assert not result.is_error
    assert result.data["hits"][0]["section"] == "Projects"
    assert "Docker" in result.text


async def test_service_error_reaches_the_model_with_its_message(stub_services, monkeypatch):
    def failing(cv_id):
        raise ServiceError("scanned PDF: no extractable text")

    monkeypatch.setattr(cv_service, "parse_cv", failing)

    async with Gateway(mcp) as gateway:
        result = await gateway.call("parse_cv", {"cv_id": CV_ID})

    assert result.is_error
    assert "scanned PDF" in result.text


async def test_unexpected_crash_does_not_leak_internals(stub_services, monkeypatch):
    def crashing(cv_id):
        raise RuntimeError("secret-internal-detail")

    monkeypatch.setattr(cv_service, "parse_cv", crashing)

    async with Gateway(mcp) as gateway:
        result = await gateway.call("parse_cv", {"cv_id": CV_ID})

    assert result.is_error
    assert "secret-internal-detail" not in result.text


@pytest.mark.parametrize(
    ("tool", "arguments"),
    [
        ("search_cv", {"cv_id": "../../etc/passwd", "query": "Docker"}),  # bad id
        ("search_cv", {"cv_id": CV_ID, "query": "x"}),  # query too short
        ("search_cv", {"cv_id": CV_ID}),  # missing argument
        ("search_cv", {"cv_id": CV_ID, "query": "Docker", "max_hits": 99}),  # over the limit
        ("verify_evidence", {"cv_id": CV_ID, "quote": "q" * 1001}),  # quote too long
    ],
)
async def test_invalid_arguments_are_rejected_before_reaching_a_service(
    stub_services, tool, arguments
):
    async with Gateway(mcp) as gateway:
        result = await gateway.call(tool, arguments)

    assert result.is_error


async def test_compute_score_accepts_models_as_arguments(stub_services):
    arguments = {
        "requirements": [{"id": 1, "text": "Python", "kind": "must"}],
        "matches": [{"requirement_id": 1, "verdict": "no", "verified": True}],
    }
    async with Gateway(mcp) as gateway:
        result = await gateway.call("compute_score", arguments)

    assert not result.is_error
    assert result.data["must_total"] == 1


async def test_toolbox_exposes_only_allowed_tools(stub_services):
    async with Gateway(mcp) as gateway:
        box = gateway.toolbox({"search_cv", "get_section"})
        names = {spec["function"]["name"] for spec in await box.specs()}

    assert names == {"search_cv", "get_section"}


async def test_toolbox_refuses_tools_outside_the_allowlist(stub_services):
    async with Gateway(mcp) as gateway:
        box = gateway.toolbox({"search_cv"})
        result = await box.call("compute_score", {"requirements": [], "matches": []})

    assert result.is_error
    assert "search_cv" in result.text  # tells the model what it can use


async def test_toolbox_runs_allowed_tools(stub_services):
    async with Gateway(mcp) as gateway:
        box = gateway.toolbox({"search_cv"})
        result = await box.call("search_cv", {"cv_id": CV_ID, "query": "Docker"})

    assert not result.is_error


async def test_using_the_gateway_before_connecting_fails_clearly():
    with pytest.raises(GatewayError):
        await Gateway(mcp).list_tools()


async def test_unreachable_gateway_raises_gateway_error():
    with pytest.raises(GatewayError):
        async with Gateway("http://127.0.0.1:1/mcp", timeout=2):
            pass


async def test_end_to_end_over_real_http(stub_services, live_gateway_url):
    async with Gateway(live_gateway_url) as gateway:
        tools = await gateway.list_tools()
        result = await gateway.call("search_cv", {"cv_id": CV_ID, "query": "Docker"})

    assert len(tools) == 5
    assert result.data["hits"][0]["text"].endswith("Docker ...")
