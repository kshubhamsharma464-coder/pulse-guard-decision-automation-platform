"""Shared "which rule pack does this request mean?" resolution logic for
the Phase 4 simulation subsystem (what-if, replay, compare). Factored out
of the three use cases that each need it (simulate_rules.py's
WhatIfSimulationUseCase, replay_simulation.py, compare_rule_packs.py)
rather than duplicated three times.

Two genuinely different sources, on purpose:
- RuleRepository.get_active(region, tenant) -- the SAME hot-path source
  EvaluateIncidentUseCase reads from (either the static 142-rule fixture
  composite or, with RULE_SOURCE=dynamic, the cache-fronted Postgres rule
  set). Resolving "the active pack" through this interface, not a copy of
  its logic, is what makes "simulate against production" mean the same
  thing simulation says it means.
- RulePackRepository.get_by_id / .get(name, version) -- the dynamic Rule
  Management platform's versioned packs (docs/rule-management.md),
  including Draft/Published versions that were never activated. This is
  how "what would rule pack v7 (still a draft) have done to this
  incident?" is answered without requiring the caller to activate a draft
  just to test it."""

from typing import Optional, Tuple

from app.domain.entities.rule_pack import RulePack
from app.domain.interfaces.rule_repository import RuleRepository
from app.domain.interfaces.rule_pack_repository import RulePackRepository


def resolve_rule_pack(
    rule_repository: RuleRepository,
    rule_pack_repository: Optional[RulePackRepository],
    *,
    pack_id: Optional[str] = None,
    name: Optional[str] = None,
    version: Optional[int] = None,
    region: Optional[str] = None,
    tenant: Optional[str] = None,
) -> Tuple[RulePack, str]:
    """Returns (pack, source_label). source_label is one of "rule_pack"
    (a specific versioned pack from RulePackRepository, resolved by id or
    name+version) or "hot_path_active" (RuleRepository.get_active() --
    whatever's actually serving POST /api/v1/incidents/evaluate right
    now). Raises ValueError with a caller-facing message if the requested
    reference doesn't resolve to anything."""
    if pack_id:
        if rule_pack_repository is None:
            raise ValueError("rulePackId was given but no rule-pack repository is configured")
        pack = rule_pack_repository.get_by_id(pack_id)
        if pack is None:
            raise ValueError(f"No such rule pack: {pack_id}")
        return pack, "rule_pack"

    if name and version is not None:
        if rule_pack_repository is None:
            raise ValueError("rulePackName/rulePackVersion was given but no rule-pack repository is configured")
        pack = rule_pack_repository.get(name, version)
        if pack is None:
            raise ValueError(f"No such rule pack: {name} v{version}")
        return pack, "rule_pack"

    if name and version is None:
        if rule_pack_repository is None:
            raise ValueError("rulePackName was given but no rule-pack repository is configured")
        pack = rule_pack_repository.get_active(name, region=region)
        if pack is None:
            raise ValueError(f"No active rule pack named '{name}' for region={region!r}")
        return pack, "rule_pack"

    pack = rule_repository.get_active(region=region, tenant=tenant)
    return pack, "hot_path_active"


def rule_pack_ref_dict(pack: RulePack, source: str) -> dict:
    """The `rulePackUsed` metadata block returned alongside every
    simulation/replay/compare response -- so a caller can always tell
    exactly what was evaluated against, not just trust it silently."""
    return {
        "source": source,
        "id": pack.id,
        "name": pack.name,
        "version": pack.version,
        "status": pack.status,
        "region": pack.region,
    }
