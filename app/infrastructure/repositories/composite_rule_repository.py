from typing import List, Optional
from app.domain.interfaces.rule_repository import RuleRepository
from app.domain.entities.rule import Rule
from app.domain.entities.rule_pack import RulePack


class CompositeRuleRepository(RuleRepository):
    """Merges Rule entities from multiple sources (e.g. the base noc-default
    pack plus the customer_sla_rules_telecom pack) into one RulePack, so
    PolicyEngine/ConflictResolver evaluate everything together in a single
    pass. This is required, not just convenient: a suppressor from one pack
    (SLA-RULE-007) has to be able to interact with a non_suppressible rule
    from another (R008, R020, R032) for the suppression semantics in design
    doc §3b to hold across pack boundaries. Running two separate pipelines
    and merging their outputs afterward could not reproduce that.

    This class only concatenates Rule lists -- it doesn't know or care where
    any individual rule originally came from or what format its source file
    used. InMemoryRuleRepository itself is untouched by this class existing;
    every existing test that constructs InMemoryRuleRepository directly still
    sees exactly the original 35 rules."""

    def __init__(self, name: str, version: int, region: Optional[str], rule_groups: List[List[Rule]]):
        merged: List[Rule] = []
        for group in rule_groups:
            merged.extend(group)
        self._pack = RulePack(name=name, version=version, status="active", region=region, rules=merged)

    def get_active(self, region: Optional[str] = None, tenant: Optional[str] = None) -> RulePack:
        return self._pack
