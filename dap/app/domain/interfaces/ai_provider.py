"""AI provider abstraction (Strategy pattern) -- every AI-assisted feature
in this codebase (NL-to-rule generation, rule documentation, decision
explanation) goes through this one interface, never a concrete SDK
directly. Swapping providers (stub -> local Llama/Ollama -> real OpenAI ->
Gemini) is a Settings.ai_provider env var change (see
app/infrastructure/ai/factory.py) -- no application or interface code
changes.

Hard safety boundary, enforced structurally, not just by convention: an
AIProvider method NEVER returns anything that becomes a Decision's
actions/priority/risk_score. generate_rule() returns a *draft* rule
payload a human (or the same rules:edit-permissioned caller) must still
explicitly POST to /api/v1/rules and then publish/activate through the
normal, deterministic lifecycle -- see
app/application/use_cases/generate_rule_from_description.py's docstring.
explain_decision() only ever runs AFTER the deterministic engine has
already produced a Decision; it describes that decision in prose, it
cannot alter it. See docs/ai-assist.md."""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class AIProvider(ABC):
    @abstractmethod
    def generate_rule(self, description: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Natural language -> a draft rule payload shaped like
        CreateRuleRequest (app/interfaces/api/schemas.py). Never persisted
        by the provider itself -- the caller (GenerateRuleFromDescriptionUseCase)
        validates it and returns it for a human to review and submit."""
        ...

    @abstractmethod
    def document_rule(self, rule: Dict[str, Any]) -> str:
        """A rule payload -> human-readable prose documentation (what it
        does, when it fires, why it exists) -- for rule-catalog docs, not
        for the decision path."""
        ...

    @abstractmethod
    def explain_decision(self, decision_facts: Dict[str, Any]) -> str:
        """A Decision's already-computed facts (matched rules, risk score,
        actions, etc.) -> a plain-language narrative explanation aimed at
        a non-technical reader (a customer service rep, not a rules
        engineer). Strictly additive to Decision.explanation (the
        deterministic, always-available explanation ExplainabilityBuilder
        already produces) -- never a substitute for it, and never fed back
        into the decision itself."""
        ...
