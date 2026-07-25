import json
from pathlib import Path
from typing import Optional
from app.domain.interfaces.rule_repository import RuleRepository
from app.domain.entities.rule import Rule
from app.domain.entities.rule_pack import RulePack
from app.domain.value_objects.rule_condition import RuleCondition

_DEFAULT_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "rules-seed.json"


class InMemoryRuleRepository(RuleRepository):
    """Fixture-backed repository -- per architecture-review.md §5, the critical path
    (policy engine + conflict resolution) is built and proven against the seeded JSON
    before wiring a real PostgreSQL-backed repository behind the same RuleRepository
    interface. Swapping in Postgres later means writing a new adapter class here;
    nothing in domain/ or application/ changes."""

    def __init__(self, path: Path = _DEFAULT_DATA_PATH):
        raw = json.loads(Path(path).read_text())
        rules = [self._parse_rule(r) for r in raw["rules"]]
        self._pack = RulePack(
            name=raw["ruleSet"]["name"],
            version=raw["ruleSet"]["version"],
            status=raw["ruleSet"]["status"],
            region=raw["ruleSet"]["region"],
            rules=rules,
        )

    def get_active(self, region: Optional[str] = None, tenant: Optional[str] = None) -> RulePack:
        return self._pack

    @staticmethod
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
