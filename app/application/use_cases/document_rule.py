from typing import Any, Dict
from app.domain.interfaces.ai_provider import AIProvider


class DocumentRuleUseCase:
    """AI-assisted rule documentation -- read-only, advisory. Never
    changes the rule; the returned text is prose for a rule catalog/README,
    not persisted anywhere by this use case."""

    def __init__(self, ai_provider: AIProvider):
        self.ai_provider = ai_provider

    def execute(self, rule: Dict[str, Any]) -> str:
        return self.ai_provider.document_rule(rule)
