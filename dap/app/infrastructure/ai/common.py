"""Shared error type + JSON-extraction helper for the LLM-backed
providers (OpenAICompatibleProvider, GeminiCompatibleProvider) -- kept
here rather than defined in (and imported from) one provider module, so
neither provider appears to depend on the other."""

import json
import re
from typing import Any, Dict


class AIProviderError(RuntimeError):
    pass


def extract_json_object(text: str) -> Dict[str, Any]:
    """LLMs frequently wrap JSON in markdown fences or add stray prose
    despite instructions not to -- strip fences, then locate the first
    top-level {...} block rather than assuming the whole string is clean
    JSON."""
    stripped = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", stripped, re.DOTALL)
    if not match:
        raise AIProviderError(f"AI response did not contain a parseable JSON object: {text[:200]!r}")
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise AIProviderError(f"AI response JSON was malformed: {exc}") from exc
