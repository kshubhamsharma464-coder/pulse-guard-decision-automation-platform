"""Unit tests for every AIProvider implementation, independent of the HTTP
API layer. StubAIProvider is tested for real (no network involved at
all). OpenAICompatibleProvider/GeminiCompatibleProvider are tested against
an httpx.MockTransport -- no live LLM endpoint is available in this
environment, but the transport injection point (added specifically for
this) lets the real prompt-building/HTTP-call/response-parsing/error-
handling code run end-to-end against a scripted fake server, which is a
materially stronger test than mocking the methods themselves."""

import json
import httpx
import pytest

from app.core.settings import Settings
from app.infrastructure.ai.factory import create_ai_provider
from app.infrastructure.ai.stub_ai_provider import StubAIProvider
from app.infrastructure.ai.openai_compatible_provider import OpenAICompatibleProvider
from app.infrastructure.ai.gemini_compatible_provider import GeminiCompatibleProvider
from app.infrastructure.ai.common import AIProviderError


# -- Factory ----------------------------------------------------------------

def test_factory_selects_stub_by_default():
    assert isinstance(create_ai_provider(Settings()), StubAIProvider)


def test_factory_selects_openai_compatible():
    assert isinstance(create_ai_provider(Settings(ai_provider="openai_compatible")), OpenAICompatibleProvider)


def test_factory_selects_gemini_compatible():
    assert isinstance(create_ai_provider(Settings(ai_provider="gemini_compatible")), GeminiCompatibleProvider)


# -- StubAIProvider (no network) --------------------------------------------

def test_stub_generate_rule_extracts_field_and_threshold():
    rule = StubAIProvider().generate_rule("If network load is greater than 90, mark high priority")
    assert rule["conditions"] == {">": [{"var": "networkLoad"}, 90]}
    assert rule["actions"]["priority"] == "High"


def test_stub_generate_rule_falls_back_conservatively_on_unrecognized_description():
    rule = StubAIProvider().generate_rule("do something clever with the flux capacitor")
    assert "REVIEW AND EDIT" in rule["description"]
    assert rule["conditions"]  # still a well-formed, non-empty condition tree


def test_stub_document_rule_is_deterministic():
    rule = {"name": "Test", "family": "NETWORK_IMPACT", "conditions": {">": [{"var": "x"}, 1]}, "actions": {"priority": "High"}}
    doc1 = StubAIProvider().document_rule(rule)
    doc2 = StubAIProvider().document_rule(rule)
    assert doc1 == doc2
    assert "Test" in doc1 and "NETWORK_IMPACT" in doc1


def test_stub_explain_decision_handles_no_matched_rules():
    text = StubAIProvider().explain_decision({"priority": None, "riskBand": "LOW", "matchedRules": []})
    assert "manual review" in text


# -- OpenAICompatibleProvider (mocked transport) ----------------------------

def _openai_transport(content: str, status_code: int = 200):
    def handler(request: httpx.Request) -> httpx.Response:
        if status_code != 200:
            return httpx.Response(status_code, json={"error": "boom"})
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})
    return httpx.MockTransport(handler)


def test_openai_compatible_generate_rule_parses_json_content():
    provider = OpenAICompatibleProvider(
        base_url="http://fake-llm/v1", api_key="k", model="llama3",
        transport=_openai_transport(json.dumps({"ruleCode": "R9", "name": "n", "conditions": {}, "actions": {}})),
    )
    result = provider.generate_rule("anything")
    assert result["ruleCode"] == "R9"


def test_openai_compatible_strips_markdown_fences():
    fenced = "```json\n" + json.dumps({"ruleCode": "R9"}) + "\n```"
    provider = OpenAICompatibleProvider(base_url="http://fake-llm/v1", api_key="k", model="llama3", transport=_openai_transport(fenced))
    assert provider.generate_rule("anything")["ruleCode"] == "R9"


def test_openai_compatible_raises_on_malformed_json():
    provider = OpenAICompatibleProvider(base_url="http://fake-llm/v1", api_key="k", model="llama3", transport=_openai_transport("not json at all"))
    with pytest.raises(AIProviderError):
        provider.generate_rule("anything")


def test_openai_compatible_raises_on_http_error():
    provider = OpenAICompatibleProvider(base_url="http://fake-llm/v1", api_key="k", model="llama3", transport=_openai_transport("", status_code=500))
    with pytest.raises(AIProviderError):
        provider.generate_rule("anything")


def test_openai_compatible_document_rule_and_explain_decision_return_plain_text():
    provider = OpenAICompatibleProvider(base_url="http://fake-llm/v1", api_key="k", model="llama3", transport=_openai_transport("  Some prose.  "))
    assert provider.document_rule({"name": "x"}) == "Some prose."
    assert provider.explain_decision({"priority": "High"}) == "Some prose."


def test_openai_compatible_raises_on_unexpected_response_shape():
    def handler(request):
        return httpx.Response(200, json={"unexpected": "shape"})
    provider = OpenAICompatibleProvider(base_url="http://fake-llm/v1", api_key="k", model="llama3", transport=httpx.MockTransport(handler))
    with pytest.raises(AIProviderError):
        provider.document_rule({"name": "x"})


# -- GeminiCompatibleProvider (mocked transport) ----------------------------

def _gemini_transport(text: str, status_code: int = 200):
    def handler(request: httpx.Request) -> httpx.Response:
        if status_code != 200:
            return httpx.Response(status_code, json={"error": "boom"})
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": text}]}}]})
    return httpx.MockTransport(handler)


def test_gemini_compatible_generate_rule_parses_json_content():
    provider = GeminiCompatibleProvider(
        base_url="https://fake-gemini/v1beta", api_key="k", model="gemini-1.5-flash",
        transport=_gemini_transport(json.dumps({"ruleCode": "G1"})),
    )
    assert provider.generate_rule("anything")["ruleCode"] == "G1"


def test_gemini_compatible_raises_on_http_error():
    provider = GeminiCompatibleProvider(base_url="https://fake-gemini/v1beta", api_key="k", model="gemini-1.5-flash", transport=_gemini_transport("", status_code=403))
    with pytest.raises(AIProviderError):
        provider.generate_rule("anything")


def test_gemini_compatible_document_rule_returns_plain_text():
    provider = GeminiCompatibleProvider(base_url="https://fake-gemini/v1beta", api_key="k", model="gemini-1.5-flash", transport=_gemini_transport("Gemini prose."))
    assert provider.document_rule({"name": "x"}) == "Gemini prose."
