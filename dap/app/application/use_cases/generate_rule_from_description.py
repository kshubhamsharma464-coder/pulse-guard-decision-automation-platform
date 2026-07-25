"""AI-assisted rule authoring -- natural language -> a draft rule payload.

Safety boundary (docs/ai-assist.md): this use case NEVER persists
anything and NEVER activates anything. It returns a draft (shaped exactly
like CreateRuleRequest) plus a ValidateRuleUseCase result -- a human (or
whatever caller holds the rules:edit permission) still has to review it
and explicitly POST it to /api/v1/rules, then publish/activate it through
the normal, fully-audited, deterministic lifecycle
(app/application/use_cases/rule_pack_lifecycle.py). The AI never gets a
path to becoming a live business decision on its own.

Deliberately returns invalid drafts too (with their validation errors
attached) rather than raising -- rejecting outright would hide exactly
the information a human reviewer needs to see and fix."""

from dataclasses import dataclass
from typing import Any, Dict, Optional

from app.domain.interfaces.ai_provider import AIProvider
from app.application.use_cases.manage_rules import ValidateRuleUseCase
from app.application.use_cases.validate_rule_pack import ValidationResult


@dataclass
class GeneratedRuleResult:
    rule: Dict[str, Any]
    validation: ValidationResult


class GenerateRuleFromDescriptionUseCase:
    def __init__(self, ai_provider: AIProvider, validator: Optional[ValidateRuleUseCase] = None):
        self.ai_provider = ai_provider
        self.validator = validator or ValidateRuleUseCase()

    def execute(
        self, description: str, family: Optional[str] = None,
        region: Optional[str] = None, sample_payload: Optional[Dict[str, Any]] = None,
    ) -> GeneratedRuleResult:
        if not description or not description.strip():
            raise ValueError("A rule description is required")

        context = {"family": family, "region": region, "samplePayload": sample_payload}
        context = {k: v for k, v in context.items() if v is not None}

        draft = self.ai_provider.generate_rule(description, context)
        draft.setdefault("ruleCode", "R-DRAFT")
        draft.setdefault("actions", {})
        draft.setdefault("conflictsWith", [])
        draft.setdefault("familyOrder", 99)
        draft.setdefault("priorityWeight", 50)
        draft.setdefault("cooldownMinutes", 0)
        if family:
            draft.setdefault("family", family)

        validation = self.validator.execute(draft)
        return GeneratedRuleResult(rule=draft, validation=validation)
