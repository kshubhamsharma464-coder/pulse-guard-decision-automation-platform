"""IActiveRuleProvider -- the Decision Engine's only dependency for "which
rules apply right now."

This is documentation-and-typing, not a new runtime abstraction: it does
NOT replace or wrap RuleRepository (app/domain/interfaces/rule_repository.py).
That decision was made explicitly back in the Phase 2.5 Rule Management
build (see docs/rule-management.md's "abstraction reuse" section) --
RuleRepository.get_active(region, tenant) -> RulePack already has exactly
the shape an "active rule provider" needs, so introducing a second,
parallel interface with the same one method would be duplication for its
own sake, not an improvement. What was missing was making that contract
explicit and separately nameable, since "IActiveRuleProvider" is how this
platform's own enterprise requirements describe it -- this module is that
explicit name.

`typing.Protocol` gives structural typing: RuleRepository (and every
concrete implementation -- InMemoryRuleRepository, CompositeRuleRepository,
PostgresRuleRepository) already satisfies IActiveRuleProvider without
inheriting from it or importing this module at all. `EvaluateIncidentUseCase`,
`WhatIfSimulationUseCase`, `ReplaySimulationUseCase`, and
`CompareRulePacksUseCase` (application layer) can be read against this
Protocol as their real contract: "give me the active rule pack for a
region/tenant" -- nothing about Postgres, Redis, JSON files, or HTTP. Swap
what's behind `dependencies.py`'s `rule_repository` (static fixture
composite, Postgres-direct, or Postgres+RuleCache+Redis) and every one of
those use cases is provably unaffected, because none of them ever import
anything from app.infrastructure -- that's the Open/Closed Principle
requirement this interface exists to make checkable, not just claimed."""

from typing import Optional, Protocol, runtime_checkable

from app.domain.entities.rule_pack import RulePack


@runtime_checkable
class IActiveRuleProvider(Protocol):
    def get_active(self, region: Optional[str] = None, tenant: Optional[str] = None) -> RulePack:
        """Returns the single rule pack that should govern decisions right
        now for this region/tenant. Implementations decide how ("static"
        fixture composite, Postgres query, Postgres query through a
        Redis-backed distributed cache) -- callers must never know or care
        which. Raises LookupError if none is configured (see
        PostgresRuleRepository's docstring for the concrete case: no rule
        pack has ever been activated yet)."""
        ...
