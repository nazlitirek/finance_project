"""Gemini sağlayıcısı: şema hazırlama, yanıt doğrulama ve hata eşlemesi (gerçek API çağrısı yok)."""

from types import SimpleNamespace

import pytest
from google.genai import errors

from app.ai import client as ai_client
from app.ai import gemini
from app.ai.client import AIError
from app.ai.schemas import AiReport, NewsBatch


def test_inline_refs_removes_defs():
    schema = gemini.inline_refs(AiReport.model_json_schema())
    text = str(schema)
    assert "$ref" not in text and "$defs" not in text
    assert schema["properties"]["technical"]["properties"]["evidence"]["type"] == "array"


class FakeInteractions:
    def __init__(self, result=None, exc=None):
        self.result, self.exc, self.kwargs = result, exc, None

    def create(self, **kw):
        self.kwargs = kw
        if self.exc:
            raise self.exc
        return self.result


def _use(monkeypatch, fake):
    monkeypatch.setattr(gemini, "_client", lambda: SimpleNamespace(interactions=fake))


def _inter(text, status="completed"):
    return SimpleNamespace(
        model="gemini-3.8-flash", id="int_1", status=status, output_text=text, errors=None,
        usage=SimpleNamespace(total_input_tokens=100, total_output_tokens=50, total_thought_tokens=20,
                              total_cached_tokens=0))


def test_structured_success_and_request_shape(monkeypatch):
    fake = FakeInteractions(_inter('{"items": []}'))
    _use(monkeypatch, fake)
    parsed, meta = gemini.structured("sistem", "kullanıcı", NewsBatch, effort="low")
    assert parsed.items == [] and meta.output_tokens == 70 and meta.extra["provider"] == "gemini"
    kw = fake.kwargs
    assert kw["system_instruction"] == "sistem" and kw["input"] == "kullanıcı"
    assert kw["response_format"]["mime_type"] == "application/json"
    assert kw["generation_config"]["thinking_level"] == "low"


@pytest.mark.parametrize(("text", "status", "kind"), [
    ('{"yanlis": 1}', "completed", "invalid_output"),
    ("", "completed", "refusal"),
    ('{"items": []}', "incomplete", "invalid_output"),
    ('{"items": []}', "failed", "error"),
])
def test_structured_bad_responses(monkeypatch, text, status, kind):
    _use(monkeypatch, FakeInteractions(_inter(text, status)))
    with pytest.raises(AIError) as e:
        gemini.structured("s", "u", NewsBatch)
    assert e.value.kind == kind


@pytest.mark.parametrize(("exc", "kind"), [
    (errors.ClientError(429, {"error": {"message": "quota"}}), "rate_limit"),
    (errors.ClientError(403, {"error": {"message": "denied"}}), "not_configured"),
    (errors.ClientError(404, {"error": {"message": "no model"}}), "error"),
    (errors.ServerError(503, {"error": {"message": "down"}}), "error"),
    (ConnectionError("dns"), "connection"),
])
def test_structured_error_mapping(monkeypatch, exc, kind):
    _use(monkeypatch, FakeInteractions(exc=exc))
    with pytest.raises(AIError) as e:
        gemini.structured("s", "u", NewsBatch)
    assert e.value.kind == kind


def test_provider_dispatch(monkeypatch):
    calls = []
    monkeypatch.setattr(ai_client, "provider", lambda: "gemini")
    monkeypatch.setattr(gemini, "structured", lambda *a, **k: calls.append("gemini") or ("ok", None))
    assert ai_client.structured("s", "u", NewsBatch)[0] == "ok" and calls == ["gemini"]
