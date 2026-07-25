"""Automatic empty-database seeding on startup (Settings.auto_seed_on_startup,
default True; docs/policy-platform.md) -- runs once per process start, only
when rule_source="dynamic" and persistence_backend="postgres" (see
main.py's lifespan handler). Idempotent and safe to run on every startup:
if an active rule pack already exists under Settings.dynamic_rule_set_name,
this is a complete no-op. It NEVER overwrites, edits, or reactivates
anything that's already there -- "seed rules are used only during first
deployment" means exactly that, not "reset to defaults on every restart."

This is the same logic scripts/seed_base_rule_pack.py has run as a
one-time manual step since Phase 1 -- extracted here so there's exactly
one seeding implementation (the script now delegates to this use case)
instead of two that could silently drift apart, and so it can also run
automatically from the FastAPI lifespan handler without duplicating a
word of it."""

from dataclasses import dataclass
from typing import Optional

from app.domain.interfaces.rule_pack_repository import RulePackRepository
from app.infrastructure.repositories.in_memory_rule_repository import InMemoryRuleRepository


@dataclass
class SeedResult:
    seeded: bool            # True only if THIS call actually created a new pack
    activated: bool         # True if an active pack exists after this call either way
    pack_name: str
    pack_version: Optional[int]


class SeedActivePolicyOnStartupUseCase:
    def __init__(self, rule_pack_repository: RulePackRepository, rule_set_name: str):
        self.rule_pack_repository = rule_pack_repository
        self.rule_set_name = rule_set_name

    def execute(self) -> SeedResult:
        existing_active = self.rule_pack_repository.get_active(self.rule_set_name, region=None)
        if existing_active is not None:
            return SeedResult(
                seeded=False, activated=True,
                pack_name=self.rule_set_name, pack_version=existing_active.version,
            )

        # The exact same 35-rule fixture the static hot path
        # (CompositeRuleRepository, rule_source="static") has always
        # loaded at startup -- reused as-is rather than a second,
        # independent seed dataset that could drift from it.
        pack = InMemoryRuleRepository().get_active()
        pack.name = self.rule_set_name

        existing_version = self.rule_pack_repository.get(pack.name, pack.version)
        saved = existing_version if existing_version is not None else self.rule_pack_repository.save(pack)
        activated = self.rule_pack_repository.activate(saved.name, saved.version)

        return SeedResult(seeded=True, activated=True, pack_name=saved.name, pack_version=activated.version)
