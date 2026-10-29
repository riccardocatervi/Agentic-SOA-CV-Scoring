import pytest
from pydantic import BaseModel

from cvscore.llm import FakeLLMClient, LLMError, LLMOutputError
from cvscore.llm.fake import structured, text, tool_call


class Answer(BaseModel):
    value: int


async def test_returns_scripted_responses_in_order():
    llm = FakeLLMClient([text("first"), text("second")])

    assert (await llm.chat([])).content == "first"
    assert (await llm.chat([])).content == "second"


async def test_records_what_it_was_asked():
    llm = FakeLLMClient([text("ok")])
    messages = [{"role": "user", "content": "hi"}]

    await llm.chat(messages, max_tokens=99)
    messages.append({"role": "user", "content": "mutated afterwards"})

    assert llm.calls[0].messages == [{"role": "user", "content": "hi"}]
    assert llm.calls[0].max_tokens == 99


async def test_extra_call_fails_loudly():
    llm = FakeLLMClient([])

    with pytest.raises(AssertionError):
        await llm.chat([])


async def test_scripted_exception_is_raised():
    llm = FakeLLMClient([LLMError("timeout")])

    with pytest.raises(LLMError):
        await llm.chat([])


async def test_tool_call_response_becomes_an_assistant_message():
    llm = FakeLLMClient([tool_call("search_cv", {"cv_id": "x", "query": "Docker"})])

    message = (await llm.chat([])).to_message()

    assert message["role"] == "assistant"
    assert message["tool_calls"][0]["function"]["name"] == "search_cv"
    assert message["tool_calls"][0]["function"]["arguments"] == '{"cv_id": "x", "query": "Docker"}'


async def test_plain_text_message_has_no_tool_calls_key():
    message = text("done").to_message()

    assert "tool_calls" not in message


@pytest.mark.parametrize(
    "wrapped",
    [
        '```json\n{"value": 3}\n```',
        '```\n{"value": 3}\n```',
        'Sure! Here is the result:\n{"value": 3}\nHope it helps.',
        '  {"value": 3}  ',
    ],
)
def test_parse_peels_code_fences_and_surrounding_prose(wrapped):
    assert text(wrapped).parse(Answer) == Answer(value=3)


def test_usage_can_be_summed():
    from cvscore.llm import Usage

    assert Usage(10, 2) + Usage(5, 1) == Usage(15, 3)


async def test_parse_validates_against_the_schema():
    assert structured(Answer(value=3)).parse(Answer) == Answer(value=3)

    with pytest.raises(LLMOutputError):
        text("not json").parse(Answer)
    with pytest.raises(LLMOutputError):
        text('{"value": "abc"}').parse(Answer)
    with pytest.raises(LLMOutputError):
        tool_call("x", {}).parse(Answer)  # no text content at all
