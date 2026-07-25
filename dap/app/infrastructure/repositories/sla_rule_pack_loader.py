"""Transpiles customer_sla_rules_telecom.json's field/operator/value +
onMatch/onNoMatch rule format into native JsonLogic Rule entities. Once
loaded, these Rule objects are indistinguishable to PolicyEngine,
ConflictResolver, RiskScorer, ExecutionPlanBuilder, and ExplainabilityBuilder
from the 35 rules in rules-seed.json -- zero changes were needed to any of
those files to support this pack. That's the point of the RuleCondition/
Rule boundary: the evaluator only ever sees our canonical shape, regardless
of what authoring format a rule pack originally arrived in.

Provenance is preserved by keeping each rule's original id (SLA-RULE-xxx)
as its rule_code rather than renaming into the R0xx namespace, so the
matched/rejected/suppressed trace on a Decision always shows which source
pack a given rule came from.

KNOWN, DELIBERATE field-namespace overlaps with the existing 35-rule pack
(see docs/customer-sla-rule-pack.md for the full list): this pack's
isDuringPlannedMaintenance / isEmergencyServiceLine / customerTier /
affectedCustomerCount are DIFFERENT fields from the existing
maintenanceWindow / emergencyServicesAffected / slaTier / affectedUsers.
Keeping them separate rather than silently aliasing them together is what
makes it provable that merging this pack in cannot change any existing
rule's behavior -- reconciling them into shared canonical fields is
documented as future work, not done here.
"""

import json
from pathlib import Path
from typing import Any, Dict, List

from app.domain.entities.rule import Rule
from app.domain.value_objects.rule_condition import RuleCondition

_DEFAULT_PATH = Path(__file__).resolve().parent.parent / "data" / "customer_sla_rules_telecom.json"

_OPERATOR_MAP = {
    "equals": "==",
    "notEquals": "!=",
    "in": "in",
    "greaterThan": ">",
    "greaterThanOrEqual": ">=",
    "lessThan": "<",
    "lessThanOrEqual": "<=",
}


def _condition_node(cond: Dict[str, Any]) -> Dict[str, Any]:
    field = cond["field"]
    operator = cond["operator"]
    value = cond["value"]
    op = _OPERATOR_MAP.get(operator)
    if op is None:
        raise ValueError(f"Unsupported condition operator '{operator}' in customer_sla_rules_telecom.json")

    if isinstance(value, str) and "*" in value:
        # Special case: a dynamic formula like "slaResponseMinutes * 0.8"
        # instead of a literal value. Only this one formula shape appears in
        # the source pack today (SLA-RULE-004); extend this if a future rule
        # needs a richer expression than "<field> * <number>".
        field_name, _, multiplier = value.partition("*")
        value = {"*": [{"var": field_name.strip()}, float(multiplier.strip())]}

    return {op: [{"var": field}, value]}


def _conditions_to_jsonlogic(conditions: List[Dict[str, Any]], logical_operator: str) -> Dict[str, Any]:
    nodes = [_condition_node(c) for c in conditions]
    if len(nodes) == 1:
        return nodes[0]
    combinator = "and" if logical_operator.upper() == "AND" else "or"
    return {combinator: nodes}


def _rule(**kwargs) -> Rule:
    kwargs.setdefault("exceptions", None)
    kwargs.setdefault("conflict_group", None)
    kwargs.setdefault("conflicts_with", [])
    kwargs.setdefault("is_suppressor", False)
    kwargs.setdefault("non_suppressible", False)
    kwargs.setdefault("cooldown_minutes", 0)
    kwargs.setdefault("mitigations", {})
    kwargs["conditions"] = RuleCondition(kwargs["conditions"])
    return Rule(**kwargs)


def load_sla_rules(path: Path = _DEFAULT_PATH) -> List[Rule]:
    raw = json.loads(Path(path).read_text())
    by_id = {r["id"]: r for r in raw["rules"]}
    rules: List[Rule] = []

    # SLA-RULE-008 -- Regulatory / Emergency Service Line. Priority 0 in the
    # source pack ("evaluates first, bypasses all other logic") maps directly
    # onto our SAFETY_REGULATORY family + non_suppressible=True pattern,
    # same tier as R008/R020/R032.
    r = by_id["SLA-RULE-008"]
    rules.append(_rule(
        rule_code=r["id"], name=r["name"], description=r["description"],
        family="SAFETY_REGULATORY", family_order=1, priority_weight=100,
        severity_band="Critical", contribution_score=None,
        conditions=_conditions_to_jsonlogic(r["conditions"], r["logicalOperator"]),
        actions={"priority": "Critical", "dispatchEngineer": True, "notifyNOC": True, "regulatoryOverride": True},
        non_suppressible=True, conflict_group="priority",
    ))

    # SLA-RULE-001 -- Platinum Tier Critical Escalation. "Regardless of raw
    # severity score" is specifically about not being diluted by the additive
    # score (contribution_score=None, same reasoning as tradeoffs.md #4) --
    # it's not marked non_suppressible, since SLA-RULE-007 already encodes
    # the Platinum maintenance-suppression exemption in its OWN condition.
    r = by_id["SLA-RULE-001"]
    rules.append(_rule(
        rule_code=r["id"], name=r["name"], description=r["description"],
        family="CUSTOMER_VALUE", family_order=3, priority_weight=88,
        severity_band="Critical", contribution_score=None,
        conditions=_conditions_to_jsonlogic(r["conditions"], r["logicalOperator"]),
        actions={"priority": "Critical", "notifyAccountManager": True},
        conflict_group="priority",
    ))

    # SLA-RULE-002 -- Customer Tier Base Weight. The source format expresses
    # this as ONE rule with a data-driven weightTable lookup; our Rule entity
    # has a single static contribution_score, so this expands into one
    # internal rule per tier value. Modifier-only (no `priority` action) --
    # never enters the priority conflict group, matches the R013-style pattern
    # already used for pure risk-score contributors.
    r = by_id["SLA-RULE-002"]
    for tier, weight in r["weightTable"].items():
        rules.append(_rule(
            rule_code=f"{r['id']}-{tier}", name=f"{r['name']} ({tier})", description=r["description"],
            family="CUSTOMER_VALUE", family_order=3, priority_weight=10,
            severity_band=None, contribution_score=weight,
            conditions={"==": [{"var": "customerTier"}, tier]},
            actions={},
        ))

    # SLA-RULE-003 -- Affected Customer Count Multiplier.
    r = by_id["SLA-RULE-003"]
    rules.append(_rule(
        rule_code=r["id"], name=r["name"], description=r["description"],
        family="NETWORK_IMPACT", family_order=2, priority_weight=15,
        severity_band=None, contribution_score=r["onMatch"]["weight"],
        conditions=_conditions_to_jsonlogic(r["conditions"], r["logicalOperator"]),
        actions={},
    ))

    # SLA-RULE-004 -- Contractual SLA Breach Risk. Uses the new "*" operator
    # for the dynamic 80%-of-response-window threshold. Its outcome is
    # labeled ESCALATE in the source but carries a `weight`, not a
    # `priorityScore` -- read as "nudge, don't force": mapped to
    # priorityBumpOneLevel (the same mechanic R013/R016 already use) plus a
    # contribution_score, not a hard priority override.
    r = by_id["SLA-RULE-004"]
    rules.append(_rule(
        rule_code=r["id"], name=r["name"], description=r["description"],
        family="CUSTOMER_VALUE", family_order=3, priority_weight=20,
        severity_band=None, contribution_score=r["onMatch"]["weight"],
        conditions=_conditions_to_jsonlogic(r["conditions"], r["logicalOperator"]),
        actions={"priorityBumpOneLevel": True, "slaBreachImminent": True},
    ))

    # SLA-RULE-005 -- Business-Critical Service Type.
    r = by_id["SLA-RULE-005"]
    rules.append(_rule(
        rule_code=r["id"], name=r["name"], description=r["description"],
        family="CUSTOMER_VALUE", family_order=3, priority_weight=10,
        severity_band=None, contribution_score=r["onMatch"]["weight"],
        conditions=_conditions_to_jsonlogic(r["conditions"], r["logicalOperator"]),
        actions={},
    ))

    # SLA-RULE-006 -- Repeat Incident Penalty.
    r = by_id["SLA-RULE-006"]
    rules.append(_rule(
        rule_code=r["id"], name=r["name"], description=r["description"],
        family="REPETITION_ESCALATION", family_order=6, priority_weight=10,
        severity_band=None, contribution_score=r["onMatch"]["weight"],
        conditions=_conditions_to_jsonlogic(r["conditions"], r["logicalOperator"]),
        actions={"chronicCustomerFlag": True},
    ))

    # SLA-RULE-007 -- Maintenance Window Suppression. Uses the new "!="
    # operator for the Platinum exclusion. Mirrors R011's suppressor pattern
    # (same conflict_group "dispatch-suppression") so it correctly interacts
    # with non_suppressible rules from EITHER pack, including SLA-RULE-008
    # and the original R008/R020/R032.
    r = by_id["SLA-RULE-007"]
    rules.append(_rule(
        rule_code=r["id"], name=r["name"], description=r["description"],
        family="SUPPRESSION", family_order=7, priority_weight=90,
        severity_band=None, contribution_score=r["onMatch"]["weight"],
        conditions=_conditions_to_jsonlogic(r["conditions"], r["logicalOperator"]),
        actions={"dispatchEngineer": False, "customerNotification": False},
        is_suppressor=True, conflict_group="dispatch-suppression",
    ))

    return rules


def load_sla_matrix(path: Path = _DEFAULT_PATH) -> Dict[str, Any]:
    raw = json.loads(Path(path).read_text())
    return raw.get("slaMatrix", {})
