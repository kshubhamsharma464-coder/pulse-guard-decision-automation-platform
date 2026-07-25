from typing import Any, Dict, List, Tuple
from app.domain.entities.rule_pack import RulePack
from app.domain.entities.incident import Incident


class ComplianceApplier:
    """Design doc §6.5 -- runs after conflict resolution, narrows execution,
    never contends for priority. COMPLIANCE rules are always non-suppressible
    by convention and evaluated independently of the priority contest."""

    def apply(self, rule_pack: RulePack, incident: Incident, actions: Dict[str, Any]) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        data = incident.as_evaluation_data()
        constraints: List[Dict[str, Any]] = []
        for rule in rule_pack.active_rules(family="COMPLIANCE"):
            if rule.conditions.is_satisfied_by(data):
                actions.update(rule.actions)
                constraints.append({"rule_code": rule.rule_code, "name": rule.name, "applied": rule.actions})
        return actions, constraints
