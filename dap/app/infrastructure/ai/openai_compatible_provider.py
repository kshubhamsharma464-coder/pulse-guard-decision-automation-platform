"""AIProvider backed by any OpenAI-compatible chat-completions endpoint --
a local Ollama/llama.cpp server (Settings' default: http://localhost:11434/v1),
or real OpenAI/Azure OpenAI, selected entirely by Settings.ai_base_url/
ai_api_key/ai_model. No SDK dependency -- a plain httpx POST, since the
chat-completions shape is simple and stable enough not to warrant pulling
in the full openai package for three call sites.

Failure handling: any network error, timeout, non-2xx response, or
unparseable output raises AIProviderError -- callers (the use cases in
app/application/use_cases/) turn that into a clear 502/504 at the API
layer. This provider never falls back to fabricating a plausible-looking
result on failure; the whole point of AI assistance is that a human
reviews real output, not a swallowed error dressed up as one."""

from typing import Any, Dict, Optional

import httpx

from app.domain.interfaces.ai_provider import AIProvider
from app.infrastructure.ai.common import AIProviderError, extract_json_object
from app.infrastructure.ai.prompts import (
    RULE_GENERATION_SYSTEM_PROMPT, RULE_DOCUMENTATION_SYSTEM_PROMPT, DECISION_EXPLANATION_SYSTEM_PROMPT,
    rule_generation_user_prompt, rule_documentation_user_prompt, decision_explanation_user_prompt,
)


class OpenAICompatibleProvider(AIProvider):
    def __init__(
        self, base_url: str, api_key: str, model: str, timeout_seconds: float = 30.0,
        transport: Optional[httpx.BaseTransport] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        # transport is None in every real deployment (httpx.Client's real
        # network transport); tests inject an httpx.MockTransport here so
        # this class's prompt-building/parsing/error-handling logic is
        # exercised without a live LLM endpoint.
        self._transport = transport

    def _chat(self, system_prompt: str, user_prompt: str, *, json_mode: bool) -> str:
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
        }
        if json_mode:
            # Most OpenAI-compatible servers (including recent Ollama)
            # support this; harmless if a given server ignores it, since
            # extract_json_object() doesn't assume it took effect.
            payload["response_format"] = {"type": "json_object"}
        try:
            with httpx.Client(transport=self._transport, timeout=self.timeout_seconds) as client:
                resp = client.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers={"Authorization": f"Bearer {self.api_key}"},
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
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise AIProviderError(f"Unexpected AI provider response shape: {data}") from exc

    def generate_rule(self, description: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        content = self._chat(
            RULE_GENERATION_SYSTEM_PROMPT, rule_generation_user_prompt(description, context or {}), json_mode=True,
        )
        return extract_json_object(content)

    def document_rule(self, rule: Dict[str, Any]) -> str:
        return self._chat(
            RULE_DOCUMENTATION_SYSTEM_PROMPT, rule_documentation_user_prompt(rule), json_mode=False,
        ).strip()

    def explain_decision(self, decision_facts: Dict[str, Any]) -> str:
        return self._chat(
            DECISION_EXPLANATION_SYSTEM_PROMPT, decision_explanation_user_prompt(decision_facts), json_mode=False,
        ).strip()
