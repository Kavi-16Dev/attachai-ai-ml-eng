"""Unit tests for the real client's retry strategy and output validation.
No network: _call_once is replaced, and sleep is injected so tests are instant."""
import pytest

from app.config import settings
from app.llm_errors import PermanentLLMError, TransientLLMError
from app.llm_providers.openai_client import OpenAILLMClient


@pytest.fixture()
def make_client(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "sk-test-not-real")

    def _make(script):
        sleeps: list[float] = []
        client = OpenAILLMClient(max_attempts=4, sleep=sleeps.append)
        calls = {"n": 0}

        def fake_call_once(_text):
            step = script[calls["n"]]
            calls["n"] += 1
            if isinstance(step, Exception):
                raise step
            return step

        client._call_once = fake_call_once
        return client, calls, sleeps

    return _make


def test_retries_transient_errors_then_succeeds(make_client):
    ok = [{"kind": "need", "text": "x", "confidence": 0.9, "restricted": False}]
    client, calls, sleeps = make_client([TransientLLMError("429"), TransientLLMError("503"), ok])
    assert client.extract_attributes("hi") == ok
    assert calls["n"] == 3
    assert len(sleeps) == 2 and sleeps[1] > 0  # backed off between tries


def test_gives_up_after_budget_as_permanent(make_client):
    client, calls, sleeps = make_client([TransientLLMError("503")] * 4)
    with pytest.raises(PermanentLLMError):
        client.extract_attributes("hi")
    assert calls["n"] == 4 and len(sleeps) == 3


def test_permanent_error_is_not_retried(make_client):
    client, calls, sleeps = make_client([PermanentLLMError("400 bad request")])
    with pytest.raises(PermanentLLMError):
        client.extract_attributes("hi")
    assert calls["n"] == 1 and sleeps == []


def test_parse_normalizes_and_clamps():
    raw = '{"attributes": [{"kind": "Need", "text": " a ", "confidence": 1.7, "restricted": false}]}'
    out = OpenAILLMClient._parse(raw)
    assert out == [{"kind": "need", "text": "a", "confidence": 1.0, "restricted": False}]


@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        '{"nope": []}',
        '{"attributes": [{"kind": "hobby", "text": "a", "confidence": 0.5, "restricted": false}]}',
        '{"attributes": [{"kind": "need", "text": "", "confidence": 0.5, "restricted": false}]}',
        '{"attributes": [{"kind": "need", "text": "a", "confidence": 0.5, "restricted": "no"}]}',
    ],
)
def test_parse_rejects_invalid_output(raw):
    with pytest.raises(PermanentLLMError):
        OpenAILLMClient._parse(raw)
