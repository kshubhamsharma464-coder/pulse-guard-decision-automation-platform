"""Transpiles telecom_incident_decision_engine_rules.json (ruleSetId
"telecom-incident-decision-engine", 30 HIS-xxx rules covering historical
failure patterns, change correlation, physical infrastructure, timing,
governance, and customer-impact signals) into native JsonLogic Rule
entities. Same transpile-to-canonical-Rule adapter pattern as the other
three merged packs; no core engine or domain-service file changes needed.

Source conditions are already valid JsonLogic (==, >=, <=, <, in, and) on
{"var": "<namespace>.<field>"} nodes, so -- like the CSR-SLA pack -- no
operator-translation table is needed, the `conditions` tree is used as-is
after one rewrite (see below).

Field-path handling: two different namespace conventions appear in the
source, and each is handled consistently with how the rest of this codebase
already treats it:
  - "incident.*" var paths are stripped to their bare name (e.g.
    "incident.relatedChangeStatus" -> "relatedChangeStatus"), exactly like
    csr_sla_rule_pack_loader.py, because Incident.as_evaluation_data()
    flattens the raw payload to the top level and this project has no
    "incident" namespace in its evaluation data.
  - "asset.*", "metrics.*", "customer.*", "change.*", "context.*" var paths
    are left as nested dotted lookups, exactly like vast_rule_pack_loader.py's
    customer.segment/request.amount/risk.fraud_score handling -- VarEvaluator
    already supports dotted paths, so the caller's incident payload simply
    needs to supply nested objects under those keys for these conditions to
    resolve. "context.*" specifically lines up with the existing
    Context Aggregation Layer's reserved "context" namespace (see
    Incident.as_evaluation_data(), which nests enriched_context there) --
    a real ContextProvider could eventually populate weatherSeverity, month,
    hourOfDay, dayOfWeek, isHoliday, gridOutageReported under that same key.
    This is a read, so it's safe regardless of whether that data exists yet:
    missing fields evaluate false, not an error.
  - Var-to-var comparisons ({"==": [{"var": "incident.affectedAsset"},
    {"var": "change.assetId"}]}, HIS002) are supported natively -- the engine
    already recursively evaluates both operands (proven by CSR-SLA-007's
    similarIncidentServiceId == serviceId case).

Action-field namespace: all 30 rules write the same seven output fields
(decision, priority, confidence, assignmentGroup, escalationLevel,
reasonCodes, slaBreachRisk). Two of those names -- "decision" and "priority"
-- are NOT safe to reuse bare here, even though grep shows no other pack
uses the literal key "priority" and only the CSR-SLA pack uses "decision":
ConflictResolver.resolve() groups writers by field name GLOBALLY across
ALL matched rules, not scoped per rule pack or per conflict_group (see its
own docstring's "known simplification" note). If this pack also wrote bare
"decision", a HIS rule and a CSR-SLA rule matching the same incident with
different conflict_groups would fall through to _merge_field's
highest-priority-weight fallback, silently overwriting one pack's decision
vocabulary with the other's -- exactly the kind of cross-pack interference
the "nothing existing should break" constraint rules out. And "priority" is
the existing categorical Critical/High/Medium/Low field used throughout the
entire system (SLA matrix lookup, risk banding, priority floors/bumps) --
this pack's P1-P5 scale is a completely different domain and must never
reach that key. So every action field here is prefixed "his" instead:
hisDecision, hisPriority, hisConfidence, hisAssignmentGroup,
hisEscalationLevel, hisReasonCodes, hisSlaBreachRisk. Checked via grep
against the full codebase (including all three previously merged packs)
before choosing this prefix -- zero collisions.

Conflict resolution: all 30 share one conflict_group ("his-decision"), using
the source pack's own 895-985 `priority` integer directly as
priority_weight -- reuses the existing weight -> specificity -> recency ->
rule_code algorithm, same as every other pack. `confidence` is preserved in
the output (hisConfidence) for audit visibility but, like the CSR-SLA pack,
does not currently participate in conflict resolution (the shared resolver
has no "confidence" tiebreak stage) -- specificity is used instead.

contribution_score is deliberately None for all 30, same reasoning as the
CSR-SLA pack: this pack's numeric priority is a routing/ordering signal for
its OWN conflict group, not a severity delta compatible with the existing
additive risk-scoring scale (0-120, banded LOW/MEDIUM/HIGH/CRITICAL).
Feeding it in would silently distort the risk band computed for any
incident this pack also matches."""

import json
from pathlib import Path
from typing import Any, Dict, List

from app.domain.entities.rule import Rule
from app.domain.value_objects.rule_condition import RuleCondition

_DEFAULT_PATH = Path(__file__).resolve().parent.parent / "data" / "telecom_incident_decision_engine_rules.json"

_FAMILY = "HISTORICAL_OPERATIONAL_PATTERN"
_FAMILY_ORDER = 12
_CONFLICT_GROUP = "his-decision"
_PREFIX = "incident."


def _strip_incident_prefix(node: Any) -> Any:
    """Recursively rewrite {"var": "incident.xxx"} -> {"var": "xxx"} through
    an arbitrary JsonLogic tree, leaving every other node (including other
    namespaces like asset./metrics./customer./change./context.) untouched."""
    if isinstance(node, dict):
        if set(node.keys()) == {"var"} and isinstance(node["var"], str) and node["var"].startswith(_PREFIX):
            return {"var": node["var"][len(_PREFIX):]}
        return {k: _strip_incident_prefix(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_strip_incident_prefix(v) for v in node]
    return node


def load_historical_pattern_rules(path: Path = _DEFAULT_PATH) -> List[Rule]:
    raw = json.loads(Path(path).read_text())
    rules: List[Rule] = []

    for r in raw["rules"]:
        then = r["actions"]
        rules.append(Rule(
            rule_code=r["id"],
            name=r["name"],
            description=r["explain"],
            family=_FAMILY,
            family_order=_FAMILY_ORDER,
            priority_weight=r["priority"],
            severity_band=None,
            contribution_score=None,
            conditions=RuleCondition(_strip_incident_prefix(r["conditions"])),
            exceptions=None,
            conflict_group=_CONFLICT_GROUP,
            conflicts_with=[],
            is_suppressor=False,
            non_suppressible=False,
            cooldown_minutes=0,
            actions={
                "hisDecision": then["decision"],
                "hisPriority": then["priority"],
                "hisConfidence": then["confidence"],
                "hisAssignmentGroup": then["assignmentGroup"],
                "hisEscalationLevel": then["escalationLevel"],
                "hisReasonCodes": then["reasonCodes"],
                "hisSlaBreachRisk": then["slaBreachRisk"],
            },
            mitigations={},
            enabled=r.get("enabled", True),
        ))

    return rules
