from typing import List, Tuple
from app.domain.entities.rule import Rule
from app.domain.entities.rule_pack import RulePack
from app.domain.entities.incident import Incident
from app.domain.entities.decision import RejectedRuleTrace

COMPLIANCE_FAMILY = "COMPLIANCE"


class PolicyEngine:
    """Evaluates every non-COMPLIANCE rule in family order (design doc §3a/§3b step 1).
    COMPLIANCE rules are evaluated separately by ComplianceApplier, after conflict
    resolution -- they never compete for priority (design doc §6.5)."""

    def evaluate(self, rule_pack: RulePack, incident: Incident) -> Tuple[List[Rule], List[RejectedRuleTrace]]:
        data = incident.as_evaluation_data()
        matched: List[Rule] = []
        rejected: List[RejectedRuleTrace] = []

        for rule in rule_pack.active_rules():
            if rule.family == COMPLIANCE_FAMILY:
                continue

            if rule.exceptions is not None and rule.exceptions.is_satisfied_by(data):
                rejected.append(RejectedRuleTrace(rule.rule_code, rule.name, "self-vetoed by exceptions clause"))
                continue

            if rule.conditions.is_satisfied_by(data):
                matched.append(rule)
            else:
                rejected.append(RejectedRuleTrace(rule.rule_code, rule.name, "conditions not satisfied"))

        return matched, rejected
