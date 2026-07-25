"""Transpiles telecom_network_infrastructure_rules.json (ruleSetId
"telecom-network-infrastructure-rules", 20 NET-INF-xxx rules) into native
Rule entities -- with a twist relative to every other merged pack: this one
is NOT purely additive at the source-rule level. Six of its 20 rules are
functional duplicates of rules already present in the CSR-SLA pack
(csr_sla_rule_pack_loader.py) -- same condition logic (byte-identical
JsonLogic tree) AND the same decision/action/escalationTarget triple, just
authored under a different rule_code with slightly different confidence
numbers. Loading them anyway would add zero new decision-making capability
while doubling up matchedRules entries and cluttering the explanation for
every incident that trips them -- so, per the explicit instruction to "skip
if it's already covered", they are excluded here rather than loaded.

All 20 source rules are still saved verbatim to the data file for
provenance/audit -- SKIPPED_RULE_IDS below is the only place the skip
decision is expressed, and it's a conscious, documented, reversible choice
(delete an entry from the set to load that rule), not a silent drop.

SKIPPED (already covered by an existing CSR-SLA-xxx rule, condition
identical or a strict subset with an identical decision/action/target):
  - NET-INF-003 "Incident Reopened Quickly" -- condition is hoursSinceClosure
    <=48, a strict subset of CSR-SLA-006's <=72, same decision/action/target
    (route_to_problem_management / problem_management). Anything that
    matches NET-INF-003 already matches CSR-SLA-006 with an identical
    outcome, so it adds no new coverage.
  - NET-INF-004 "Similar Incident Within One Hour" -- condition byte-
    identical to CSR-SLA-007, same decision/target; only the action string
    differs cosmetically (attach_to_parent_incident vs
    attach_to_existing_incident) for the same intent.
  - NET-INF-005 "Historical Outage Frequency" -- condition byte-identical to
    CSR-SLA-008, same decision/action/target.
  - NET-INF-006 "Low MTBF Chronic Equipment" -- condition byte-identical to
    CSR-SLA-010, same decision/action/target.
  - NET-INF-009 "Maintenance Window Suppression" -- condition byte-identical
    to CSR-SLA-012, same decision/action/target.
  - NET-INF-011 "SLA Breach Imminent" -- condition byte-identical to
    CSR-SLA-003, same decision/action/target.

NOT skipped despite thematic overlap, because the condition, action, or
escalation target is materially different (see docs/customer-sla-rule-pack.md
for the full rule-by-rule rationale) -- most notably:
  - NET-INF-002 adds an extra mtbfHours condition on top of CSR-SLA-005's
    tower-failure condition and routes to ran_engineering instead of
    engineering_oncall -- a genuinely more specific companion rule, not a
    duplicate.
  - NET-INF-010 shares CSR-SLA-013's exact condition (unapproved maintenance
    with customer impact) but disagrees on escalationTarget
    (engineering_oncall vs CSR-SLA-013's noc_level_3) -- a real cross-pack
    policy disagreement on the same trigger, surfaced rather than silently
    resolved (same treatment as the CSR-021/CSR-001 tie in the vast pack).
  - NET-INF-016, 018, 019 reuse a CSR-SLA action name but key off different
    fields/thresholds entirely (customerSegment vs isOpen; mttrHours vs
    impactScope; equipmentFailures30d vs repeatFailures90d) -- different
    triggering logic, kept as independent rules.

Field-path handling and action-field namespace follow the same conventions
established for the CSR-SLA and HIS packs: "incident." var paths are
stripped to their bare top-level name; all output fields are prefixed
"netInf" -- netInfDecision, netInfAction, netInfEscalationTarget,
netInfPriorityScore, netInfConfidence, netInfExplanation. This is NOT
optional here the way it might look: the CSR-SLA pack already writes bare
"decision" and "escalationTarget" action keys, and ConflictResolver groups
writers by field name globally across all matched rules regardless of pack
or conflict_group (see its "known simplification" docstring, and the HIS
pack's loader for the first time this was flagged). NET-INF-010 in
particular disagrees with CSR-SLA-013 on escalationTarget for the exact
same condition -- if both wrote the bare "escalationTarget" key, one pack's
routing recommendation would silently overwrite the other's. Namespacing
NET-INF's fields keeps both packs' opinions independently visible in the
decision output instead."""

import json
from pathlib import Path
from typing import Any, Dict, List

from app.domain.entities.rule import Rule
from app.domain.value_objects.rule_condition import RuleCondition

_DEFAULT_PATH = Path(__file__).resolve().parent.parent / "data" / "telecom_network_infrastructure_rules.json"

_FAMILY = "NETWORK_INFRASTRUCTURE_PATTERN"
_FAMILY_ORDER = 13
_CONFLICT_GROUP = "net-inf-decision"
_PREFIX = "incident."

SKIPPED_RULE_IDS = {
    "NET-INF-003": "duplicate of CSR-SLA-006 (Incident Reopened Quickly) -- strict subset condition, identical outcome",
    "NET-INF-004": "duplicate of CSR-SLA-007 (Similar Incident Within One Hour) -- identical condition and outcome",
    "NET-INF-005": "duplicate of CSR-SLA-008 (Historical Outage Frequency High) -- identical condition and outcome",
    "NET-INF-006": "duplicate of CSR-SLA-010 (Low MTBF Chronic Equipment) -- identical condition and outcome",
    "NET-INF-009": "duplicate of CSR-SLA-012 (Maintenance Window Suppression) -- identical condition and outcome",
    "NET-INF-011": "duplicate of CSR-SLA-003 (SLA Breach Imminent) -- identical condition and outcome",
}


def _strip_incident_prefix(node: Any) -> Any:
    if isinstance(node, dict):
        if set(node.keys()) == {"var"} and isinstance(node["var"], str) and node["var"].startswith(_PREFIX):
            return {"var": node["var"][len(_PREFIX):]}
        return {k: _strip_incident_prefix(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_strip_incident_prefix(v) for v in node]
    return node


def load_net_inf_rules(path: Path = _DEFAULT_PATH) -> List[Rule]:
    raw = json.loads(Path(path).read_text())
    rules: List[Rule] = []

    for r in raw["rules"]:
        if r["ruleId"] in SKIPPED_RULE_IDS:
            continue

        then = r["then"]
        rules.append(Rule(
            rule_code=r["ruleId"],
            name=r["name"],
            description=then["explanation"],
            family=_FAMILY,
            family_order=_FAMILY_ORDER,
            priority_weight=r["priority"],
            severity_band=None,
            contribution_score=None,
            conditions=RuleCondition(_strip_incident_prefix(r["when"])),
            exceptions=None,
            conflict_group=_CONFLICT_GROUP,
            conflicts_with=[],
            is_suppressor=False,
            non_suppressible=False,
            cooldown_minutes=0,
            actions={
                "netInfDecision": then["decision"],
                "netInfAction": then["action"],
                "netInfEscalationTarget": then["escalationTarget"],
                "netInfPriorityScore": then["priority"],
                "netInfConfidence": then["confidence"],
                "netInfExplanation": then["explanation"],
            },
            mitigations={},
            enabled=r.get("enabled", True),
        ))

    return rules
