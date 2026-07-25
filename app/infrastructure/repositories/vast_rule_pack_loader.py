"""Transpiles customer_sla_rules_vast.json's when/then rule format (30
CSR-xxx rules) into native JsonLogic Rule entities, same pattern as
sla_rule_pack_loader.py. This pack is genuinely a different DECISIONING
VERTICAL than the other two -- it's a generic customer-request workflow
(customer.segment, request.amount, risk.fraud_score), not telecom incidents
-- so rather than force-fitting its rules into the existing 8 telecom
families, they get one new family, CUSTOMER_REQUEST_WORKFLOW. No core file
(PolicyEngine, ConflictResolver, RiskScorer, etc.) needed to change to add
a new family: only PolicyEngine hardcodes a family name at all (COMPLIANCE,
to exclude it from the priority contest), and this pack doesn't use it.

Field paths are dotted (customer.segment, request.amount, sla.hours_remaining,
risk.fraud_score) -- RuleCondition's underlying VarEvaluator already
supports dotted lookups, so no engine change was needed for that either.

All 30 rules write the same two new action fields (customerDecision,
customerAction) and share one conflict_group ("customer-decision"), so a
conflicting match between e.g. an "approve" rule and a "deny" rule is
resolved by the SAME weight/specificity/rule_code tiebreak already used
throughout the rest of the rule base (design doc §3b) -- reused unchanged.

Deliberate deviation from the source data, flagged rather than silent:
CSR-021 (Fraud Risk Block, priority 100) ties with CSR-001 (Enterprise
Priority, also priority 100). Our tiebreak (equal specificity, then
rule_code ascending) would let "CSR-001" beat "CSR-021" alphabetically --
i.e. a high-fraud-risk enterprise customer would see "approve/escalate" win
over "deny/block". That's very likely not the intended business outcome, so
CSR-021's priority_weight is bumped from 100 to 105 here to give the fraud
block an unambiguous, deterministic win. This is a value judgment call, not
a mechanical transpile step -- it needs real business sign-off, and is
called out again in docs/customer-sla-rule-pack.md."""

import json
from pathlib import Path
from typing import Any, Dict, List

from app.domain.entities.rule import Rule
from app.domain.value_objects.rule_condition import RuleCondition

_DEFAULT_PATH = Path(__file__).resolve().parent.parent / "data" / "customer_sla_rules_vast.json"

_OPERATOR_MAP = {
    "equals": "==",
    "lte": "<=",
    "gte": ">=",
    "lt": "<",
    "gt": ">",
    "in": "in",
    "contains": "contains",
    "in_holiday_period": "in_holiday_period",
}

_PRIORITY_OVERRIDES = {
    "CSR-021": 105,  # see module docstring -- breaks an unintended tie with CSR-001
}

_FAMILY = "CUSTOMER_REQUEST_WORKFLOW"
_FAMILY_ORDER = 10
_CONFLICT_GROUP = "customer-decision"


def _condition_node(cond: Dict[str, Any]) -> Dict[str, Any]:
    field = cond["field"]
    op = _OPERATOR_MAP.get(cond["op"])
    if op is None:
        raise ValueError(f"Unsupported condition operator '{cond['op']}' in customer_sla_rules_vast.json")
    return {op: [{"var": field}, cond["value"]]}


def _when_to_jsonlogic(when: Dict[str, Any]) -> Dict[str, Any]:
    if "all" in when:
        nodes = [_condition_node(c) for c in when["all"]]
        return nodes[0] if len(nodes) == 1 else {"and": nodes}
    if "any" in when:
        nodes = [_condition_node(c) for c in when["any"]]
        return nodes[0] if len(nodes) == 1 else {"or": nodes}
    raise ValueError(f"Unsupported 'when' shape: {when!r}")


def load_vast_rules(path: Path = _DEFAULT_PATH) -> List[Rule]:
    raw = json.loads(Path(path).read_text())
    rules: List[Rule] = []

    for r in raw["rules"]:
        rule_id = r["rule_id"]
        rules.append(Rule(
            rule_code=rule_id,
            name=r["name"],
            description=r["then"]["reason"],
            family=_FAMILY,
            family_order=_FAMILY_ORDER,
            priority_weight=_PRIORITY_OVERRIDES.get(rule_id, r["priority"]),
            severity_band=None,
            contribution_score=r["then"]["score_delta"],
            conditions=RuleCondition(_when_to_jsonlogic(r["when"])),
            exceptions=None,
            conflict_group=_CONFLICT_GROUP,
            conflicts_with=[],
            is_suppressor=False,
            non_suppressible=False,
            cooldown_minutes=0,
            actions={
                "customerDecision": r["then"]["decision"],
                "customerAction": r["then"]["action"],
            },
            mitigations={},
            enabled=r.get("enabled", True),
        ))

    return rules
