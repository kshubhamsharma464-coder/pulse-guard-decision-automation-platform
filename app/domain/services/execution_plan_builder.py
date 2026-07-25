from typing import Any, Dict, List
from app.domain.entities.rule import Rule

_BASE_PRECEDENCE = [
    ("autoRemediate", "Automated Remediation"),
    ("rerouteTraffic", "Traffic Reroute"),
    ("dispatchEngineer", "Dispatch Engineer"),
    ("customerNotification", "Customer Notification"),
    ("notifyNOC", "Notify NOC"),
]


class ExecutionPlanBuilder:
    """Design doc §3d -- turns the flat merged actions dict into an ordered plan,
    honoring per-rule `sequencing` retry/fallback hints (e.g. try remote restart
    before dispatching an engineer)."""

    def build(self, actions: Dict[str, Any], matched: List[Rule]) -> List[Dict[str, Any]]:
        plan: List[Dict[str, Any]] = []
        order = 1
        inserted_types = set()

        for rule in [r for r in matched if r.sequencing]:
            seq = rule.sequencing
            plan.append({"order": order, "action": seq["tryFirst"], "type": seq["tryFirst"], "source": rule.rule_code})
            order += 1
            plan.append({
                "order": order, "action": seq["fallbackTo"], "type": seq["fallbackTo"],
                "condition": f"if {seq['tryFirst']} fails within {seq.get('fallbackAfterMinutes', '?')} minutes",
                "source": rule.rule_code,
            })
            order += 1
            inserted_types.add(seq["tryFirst"])
            inserted_types.add(seq["fallbackTo"])

        for field_name, label in _BASE_PRECEDENCE:
            if actions.get(field_name) and field_name not in inserted_types:
                plan.append({"order": order, "action": label, "type": field_name})
                order += 1

        return plan
