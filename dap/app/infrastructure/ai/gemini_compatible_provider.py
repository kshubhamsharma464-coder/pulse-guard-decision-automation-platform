"""AIProvider backed by Google's Gemini REST API (generateContent). A
separate implementation from OpenAICompatibleProvider rather than one
provider with an if-branch, because Gemini's request/response shape
(contents/parts, systemInstruction, candidates) is genuinely different
from OpenAI's chat-completions shape, not just a different base URL --
this is exactly the "adding a provider never touches existing code"
Strategy-pattern property the interface exists for.

When Settings.ai_provider="gemini_compatible", also set
AI_BASE_URL=https://generativelanguage.googleapis.com/v1beta (see
.env.example) and AI_API_KEY to a real Gemini API key -- AI_MODEL
defaults to "llama3" for the Ollama case and should be changed to a real
Gemini model name (e.g. "gemini-1.5-flash")."""

from typing import Any, Dict, Optional

import httpx

from app.domain.interfaces.ai_provider import AIProvider
from app.infrastructure.ai.common import AIProviderError, extract_json_object
from app.infrastructure.ai.prompts import (
    RULE_GENERATION_SYSTEM_PROMPT, RULE_DOCUMENTATION_SYSTEM_PROMPT, DECISION_EXPLANATION_SYSTEM_PROMPT,
    rule_generation_user_prompt, rule_documentation_user_prompt, decision_explanation_user_prompt,
)


class GeminiCompatibleProvider(AIProvider):
    def __init__(
        self, base_url: str, api_key: str, model: str, timeout_seconds: float = 30.0,
        transport: Optional[httpx.BaseTransport] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self._transport = transport  # see OpenAICompatibleProvider's docstring for why

    def _generate(self, system_prompt: str, user_prompt: str) -> str:
        payload = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "generationConfig": {"temperature": 0.2},
        }
        try:
            with httpx.Client(transport=self._transport, timeout=self.timeout_seconds) as client:
                resp = client.post(
                    f"{self.base_url}/models/{self.model}:generateContent",
                    params={"key": self.api_key},
                    json=payload,
                )
            resp.raise_for_status()
        except httpx.TimeoutException as exc:
            raise AIProviderError(f"AI provider request timed out after {self.timeout_seconds}s") from exc
        except httpx.HTTPStatusError as exc:
            raise AIProviderError(f"AI provider returned HTTP {exc.response.status_code}: {exc.response.text[:300]}") from exc
        except httpx.HTTPError as exc:
            raise AIProviderError(f"AI provider request failed: {exc}") from exc

        data = resp.json()
        try:
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError) as exc:
            raise AIProviderError(f"Unexpected AI provider response shape: {data}") from exc

    def generate_rule(self, description: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        content = self._generate(RULE_GENERATION_SYSTEM_PROMPT, rule_generation_user_prompt(description, context or {}))
        return extract_json_object(content)

    def document_rule(self, rule: Dict[str, Any]) -> str:
        return self._generate(RULE_DOCUMENTATION_SYSTEM_PROMPT, rule_documentation_user_prompt(rule)).strip()

    def explain_decision(self, decision_facts: Dict[str, Any]) -> str:
        return self._generate(DECISION_EXPLANATION_SYSTEM_PROMPT, decision_explanation_user_prompt(decision_facts)).strip()
