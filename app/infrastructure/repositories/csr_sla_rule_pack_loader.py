"""Transpiles csr_sla_decision_rules.json (ruleSetId "telecom-customer-sla-rules",
18 CSR-SLA-xxx rules) into native JsonLogic Rule entities -- same
transpile-to-canonical-Rule adapter pattern as sla_rule_pack_loader.py and
vast_rule_pack_loader.py. No core engine or domain-service file changes were
needed to add this pack.

Source shape per rule: {ruleId, version, name, enabled, priority (0-999),
confidence (0-1), category, when: {and:[{op: [...]}]}, then: {decision,
action, escalationTarget, priority, confidence, explanation}}. Conditions
use JsonLogic operators directly (==, in, <=, >=) rather than a custom
{field, op, value} shape, so no operator translation table is needed here
(unlike the SLA and vast loaders) -- the source `when` tree IS already a
valid JsonLogic tree and is used as-is.

Field-path prefix stripping: every var path in the source is prefixed
"incident." (e.g. "incident.customerTier"), a namespace this project's
Incident.as_evaluation_data() does not use -- that method flattens the raw
incident payload straight to the top level (see app/domain/entities/incident.py).
Rather than change the shared evaluation-data shape (which every existing
rule and test depends on), the "incident." prefix is stripped at load time
so these conditions resolve against the same flat top-level fields every
other pack already reads. This is read-only: multiple packs reading a
shared field name (e.g. "customerTier", also read by sla_rule_pack_loader.py)
is always safe: it's only concurrent *writes* to the same field that need
isolation, and this pack owns an entirely new set of output fields (see
below), so no write collision is possible.

Action-field namespace: all 18 rules write the SAME five output fields --
decision, csrSlaAction, escalationTarget, csrSlaPriorityScore,
csrSlaConfidence, csrSlaExplanation -- prefixed csrSla (except the shared
"decision"/"escalationTarget" names, checked against the full codebase via
grep and confirmed not used as an actions-dict key anywhere else; the API's
outer envelope key "decision" in serializers.py wraps the *entire* actions
dict, so a same-named inner key just nests, it does not overwrite anything).
Because all 18 share one output-field set, they also share one
conflict_group ("csr-sla-priority-decision") so a genuine multi-match (e.g.
Gold escalation + High Revenue Risk both firing) is resolved by the existing
weight -> specificity -> recency -> rule_code algorithm, using the source
pack's own 300-960 `priority` integer as priority_weight. This reuses,
rather than reimplements, the one conflict-resolution algorithm already used
by every other pack in the system (per architecture-review.md's preference
for a single deterministic algorithm, not per-pack custom logic).

Known, documented simplification: the source pack declares
defaultConflictPolicy "highest_priority_then_highest_confidence_then_newest_version".
Our shared resolver's tiebreak order is weight -> specificity -> recency ->
rule_code -- it does not currently have a "confidence" tiebreak stage.
`confidence` is preserved in the output (csrSlaConfidence) for downstream/
audit visibility but does not participate in conflict resolution; specificity
is used as the generic secondary criterion instead, consistent with every
other pack. Flagged here and in docs/customer-sla-rule-pack.md rather than
adding a pack-specific resolver branch.

contribution_score is deliberately None for all 18 rules: this pack's
numeric `priority` (300-960) is a routing/ordering signal for ITS OWN
conflict group, not a severity delta compatible with the existing additive
risk-scoring scale (0-120, banded LOW/MEDIUM/HIGH/CRITICAL) used by the base
35-rule pack. Feeding it in would silently distort the existing risk band
for every incident this pack matches -- exactly the kind of cross-pack
interference the "nothing existing should break" constraint rules out. So
these rules affect only their own five csrSla*/decision/escalationTarget
fields and never enter riskScore/riskBand at all."""

import json
from pathlib import Path
from typing import Any, Dict, List

from app.domain.entities.rule import Rule
from app.domain.value_objects.rule_condition import RuleCondition

_DEFAULT_PATH = Path(__file__).resolve().parent.parent / "data" / "csr_sla_decision_rules.json"

_FAMILY = "CUSTOMER_SLA_PRIORITY"
_FAMILY_ORDER = 11
_CONFLICT_GROUP = "csr-sla-priority-decision"
_PREFIX = "incident."


def _strip_incident_prefix(node: Any) -> Any:
    """Recursively rewrite {"var": "incident.xxx"} -> {"var": "xxx"} through
    an arbitrary JsonLogic tree, leaving every other node untouched."""
    if isinstance(node, dict):
        if set(node.keys()) == {"var"} and isinstance(node["var"], str) and node["var"].startswith(_PREFIX):
            return {"var": node["var"][len(_PREFIX):]}
        return {k: _strip_incident_prefix(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_strip_incident_prefix(v) for v in node]
    return node


def load_csr_sla_rules(path: Path = _DEFAULT_PATH) -> List[Rule]:
    raw = json.loads(Path(path).read_text())
    rules: List[Rule] = []

    for r in raw["rules"]:
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
                "decision": then["decision"],
                "csrSlaAction": then["action"],
                "escalationTarget": then["escalationTarget"],
                "csrSlaPriorityScore": then["priority"],
                "csrSlaConfidence": then["confidence"],
                "csrSlaExplanation": then["explanation"],
            },
            mitigations={},
            enabled=r.get("enabled", True),
        ))

    return rules
