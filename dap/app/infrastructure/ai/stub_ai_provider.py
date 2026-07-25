"""Deterministic, offline, zero-configuration AIProvider -- the default
(Settings.ai_provider="stub"). No network calls, so it works in any
environment (including this project's own test suite and sandboxes with
no outbound network access) without a local Llama/Ollama server or a real
API key. Uses keyword/heuristic extraction rather than an LLM -- honest
about being a stand-in, not pretending to understand arbitrary prose the
way a real model would. Swapping to OpenAICompatibleProvider (pointed at
a local Ollama server or real OpenAI) is a single env var
(AI_PROVIDER=openai_compatible), no code change."""

import re
from typing import Any, Dict, Optional

from app.domain.interfaces.ai_provider import AIProvider

_FIELD_KEYWORDS = {
    "affected users": "affectedUsers", "affecteduser": "affectedUsers", "users affected": "affectedUsers",
    "network load": "networkLoad", "load": "networkLoad",
    "historical failures": "historicalFailures", "past failures": "historicalFailures",
    "vip": "vipCustomersAffected",
    "sla tier": "slaTier", "gold": "slaTier", "silver": "slaTier", "bronze": "slaTier",
    "weather": "weatherSeverity",
    "maintenance window": "maintenanceWindow", "maintenance": "maintenanceWindow",
    "emergency services": "emergencyServicesAffected",
    "region": "region",
}

_THRESHOLD_RE = re.compile(
    r"(greater than|more than|over|above|exceeds?|>)\s*([\d,]+)|(less than|under|below|<)\s*([\d,]+)",
    re.IGNORECASE,
)

_ACTION_KEYWORDS = {
    "critical": ("priority", "Critical"), "high priority": ("priority", "High"),
    "dispatch": ("dispatchEngineer", True), "engineer": ("dispatchEngineer", True),
    "notify noc": ("notifyNOC", True), "notify the noc": ("notifyNOC", True),
    "reroute": ("rerouteTraffic", True),
}


class StubAIProvider(AIProvider):
    def generate_rule(self, description: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        context = context or {}
        lowered = description.lower()

        field = next((v for k, v in _FIELD_KEYWORDS.items() if k in lowered), None)
        threshold_match = _THRESHOLD_RE.search(description)

        assumptions = []
        if field and threshold_match:
            operator = ">" if threshold_match.group(2) else "<"
            value_str = (threshold_match.group(2) or threshold_match.group(4)).replace(",", "")
            try:
                value: Any = int(value_str)
            except ValueError:
                value = value_str
            conditions = {operator: [{"var": field}, value]}
        elif field:
            # A field was recognized but no numeric threshold -- fall back to
            # a boolean/equality-truthy check rather than fabricating a number.
            conditions = {"==": [{"var": field}, True]}
            assumptions.append(f"no explicit threshold found for '{field}'; assumed a boolean/truthy check")
        else:
            # Nothing recognizable -- conservative, clearly-flagged fallback
            # rather than inventing a plausible-looking but meaningless rule.
            conditions = {"==": [{"var": "incidentType"}, "Tower Down"]}
            assumptions.append(
                "could not identify a specific field/threshold from the description; "
                "defaulted to incidentType == 'Tower Down' -- REVIEW AND EDIT CONDITIONS before publishing"
            )

        actions: Dict[str, Any] = {}
        for keyword, (action_field, action_value) in _ACTION_KEYWORDS.items():
            if keyword in lowered:
                actions[action_field] = action_value
        if not actions:
            actions = {"priority": "Medium"}
            assumptions.append("no explicit action keywords found; defaulted actions to priority=Medium")

        family = context.get("family") or "OPERATIONAL_FEASIBILITY"
        rule_desc = description.strip()
        if assumptions:
            rule_desc += " [stub-generated assumptions: " + "; ".join(assumptions) + "]"

        return {
            "ruleCode": "R-DRAFT-STUB",
            "name": description.strip()[:80] or "Untitled rule",
            "description": rule_desc,
            "family": family,
            "familyOrder": 99,
            "priorityWeight": 50,
            "severityBand": None,
            "contributionScore": None,
            "conditions": conditions,
            "conflictsWith": [],
            "actions": actions,
            "cooldownMinutes": 0,
        }

    def document_rule(self, rule: Dict[str, Any]) -> str:
        name = rule.get("name", "This rule")
        family = rule.get("family", "an unspecified")
        conditions = rule.get("conditions", {})
        actions = rule.get("actions", {})
        cond_summary = _summarize_conditions(conditions)
        action_summary = ", ".join(f"{k}={v}" for k, v in actions.items()) or "no explicit actions"
        return (
            f"{name} belongs to the {family} rule family. It fires when {cond_summary}. "
            f"When triggered, it sets: {action_summary}."
        )

    def explain_decision(self, decision_facts: Dict[str, Any]) -> str:
        priority = decision_facts.get("priority") or "an unclassified priority"
        risk_band = decision_facts.get("riskBand", "an unknown")
        matched = decision_facts.get("matchedRules", [])
        rule_names = ", ".join(m.get("name", m.get("rule_code", "a rule")) for m in matched[:3])
        more = f" and {len(matched) - 3} other rule(s)" if len(matched) > 3 else ""
        if not matched:
            return (
                f"This incident was assigned {priority} priority. No specific business rule matched, "
                f"so it has been routed for manual review."
            )
        return (
            f"This incident was assigned {priority} priority, primarily because of: {rule_names}{more}. "
            f"The overall risk level was assessed as {risk_band}, which reflects the combination of "
            f"factors involved but did not itself determine the priority -- the matched business rules did."
        )


def _summarize_conditions(node: Dict[str, Any]) -> str:
    if not isinstance(node, dict) or not node:
        return "its conditions are met"
    operator, args = next(iter(node.items()))
    if operator in ("and", "or") and isinstance(args, list):
        parts = [_summarize_conditions(a) for a in args]
        joiner = " and " if operator == "and" else " or "
        return joiner.join(parts)
    if isinstance(args, list) and len(args) == 2:
        left, right = args
        field = left.get("var") if isinstance(left, dict) else left
        return f"{field} {operator} {right}"
    return f"the '{operator}' condition is satisfied"
