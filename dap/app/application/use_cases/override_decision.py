import uuid
from datetime import datetime, timezone
from typing import Any, Dict
from app.domain.entities.decision import Decision
from app.domain.entities.manual_override import ManualOverride
from app.domain.interfaces.manual_override_repository import ManualOverrideRepository


class OverrideDecisionUseCase:
    """Design doc §6.6: the automated decision is never mutated. An override
    is a separate, fully audited record referencing it -- this is what makes
    "the engine was right, an operator had situational information it didn't"
    distinguishable from "the engine was wrong" after the fact."""

    def __init__(self, repository: ManualOverrideRepository = None):
        self.repository = repository

    def execute(self, decision: Decision, operator: str, override_actions: Dict[str, Any], reason: str) -> ManualOverride:
        if not operator or not operator.strip():
            raise ValueError("A manual override requires an identified operator")
        if not reason or not reason.strip():
            raise ValueError("A manual override requires a non-empty reason -- this is an audit record, not a shortcut")

        override = ManualOverride(
            id=str(uuid.uuid4()),
            decision_id=decision.incident_id,
            operator=operator,
            original_decision=dict(decision.actions),
            override_decision=override_actions,
            reason=reason,
            created_at=datetime.now(timezone.utc),
        )
        if self.repository is not None:
            self.repository.save(override)
        return override
