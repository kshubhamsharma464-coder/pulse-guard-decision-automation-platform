"""Loads industry_sop_rules.json -- unlike every other merged pack, this one
is NOT a transpiled third-party schema. It's authored directly in this
project's own native Rule schema (identical field names to rules-seed.json:
ruleCode/family/familyOrder/priorityWeight/conflictGroup/etc.), because
these three rules were written by auditing the existing rule base against
real telecom NOC / ITIL industry SOPs, not by adapting an externally-pasted
JSON pack. Parsing is therefore a direct 1:1 field mapping, not a
condition-tree transpile -- deliberately mirrors
InMemoryRuleRepository._parse_rule exactly (same field names, same
defaults) rather than introducing a second, subtly-different native parser.

The audit that produced this pack (see docs/industry-sop-gap-closure.md for
the full writeup) found that most standard NOC SOP categories were already
covered by the original 35-rule base pack, in some cases anticipated but
left unfilled: R015/R032 already route security incidents (DDoS,
unauthorized access) to the SOC; R029 already implements auto-remediation-
before-escalation for a known firmware bug; R017 already declares major
incidents and notifies executives on regional storm thresholds; R008/R020
already trigger regulatory reporting for emergency-services impact; R010/
R023/R037 already handle weather/capacity/security-zone dispatch
feasibility; R030/R031 already handle government/GDPR compliance
constraints. The base pack's own `families` metadata even explicitly notes
"security incidents" under SAFETY_REGULATORY, and its action-field
vocabulary already declares `escalateVendor` -- but grep confirmed no rule
anywhere in the base pack ever actually sets it. That is the genuine gap
this pack closes, along with two other verified-absent SOP concepts (change
freeze governance, and the separate mass-outage-scale regulatory reporting
trigger, as opposed to the emergency-services-line trigger R008/R020
already handle).

Because these three rules extend concepts the base pack's OWN vocabulary
already established (escalateVendor, regulatoryReportingRequired,
regulatoryReportingDeadlineHours, notifyNOC, priorityFloor,
priorityBumpOneLevel are all base-pack fields, confirmed via grep before
reuse), they deliberately reuse those exact field names and slot into the
base pack's OWN family taxonomy (OPERATIONAL_FEASIBILITY, TEMPORAL,
SAFETY_REGULATORY) rather than inventing a new isolated family/namespace
the way the customer-workflow-vertical packs (vast, CSR-SLA, HIS, NET-INF)
correctly did. This is a deliberate, different integration choice: those
four packs represent different decisioning verticals or third-party
authorship and needed isolation; these three rules are direct extensions of
the SAME incident-triage vertical the base 35 rules already model, so
joining the existing vocabulary is the more correct design, not a
shortcut -- and it's safe for the same reason SLA-RULE-001/008 safely
joined the base pack's "priority" conflict_group in the very first merged
pack: these rules use genuinely new, grep-verified-unused CONDITION field
names (rootCauseVendorAttributed, vendorContractHasUpc, changeFreezeActive,
changeLinkedToIncident, changeEmergencyApproved, outageDurationMinutes), so
they cannot match any existing test's incident payload and cannot change
any existing test's outcome."""

import json
from pathlib import Path
from typing import List

from app.domain.entities.rule import Rule
from app.domain.value_objects.rule_condition import RuleCondition

_DEFAULT_PATH = Path(__file__).resolve().parent.parent / "data" / "industry_sop_rules.json"


def _parse_rule(r: dict) -> Rule:
    return Rule(
        rule_code=r["ruleCode"],
        name=r["name"],
        description=r.get("description", ""),
        family=r["family"],
        family_order=r["familyOrder"],
        priority_weight=r["priorityWeight"],
        severity_band=r.get("severityBand"),
        contribution_score=r.get("contributionScore"),
        conditions=RuleCondition(r["conditions"]),
        exceptions=RuleCondition(r["exceptions"]) if r.get("exceptions") else None,
        conflict_group=r.get("conflictGroup"),
        conflicts_with=r.get("conflictsWith", []),
        is_suppressor=r.get("isSuppressor", False),
        non_suppressible=r.get("nonSuppressible", False),
        cooldown_minutes=r.get("cooldownMinutes", 0),
        actions=r.get("actions", {}),
        mitigations=r.get("mitigations", {}),
        sequencing=r.get("sequencing"),
        sla_target=r.get("slaTarget"),
        rule_status=r.get("ruleStatus", "ACTIVE"),
        enabled=True,
    )


def load_industry_sop_rules(path: Path = _DEFAULT_PATH) -> List[Rule]:
    raw = json.loads(Path(path).read_text())
    return [_parse_rule(r) for r in raw["rules"]]
