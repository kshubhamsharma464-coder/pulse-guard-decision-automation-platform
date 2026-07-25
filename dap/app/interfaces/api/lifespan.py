"""FastAPI lifespan handler -- the concrete "Application Startup -> Load
Active Policy -> Compile Rules -> Store in Redis -> Serve Requests"
sequence (docs/policy-platform.md), and its shutdown counterpart.

Two steps, both no-ops in every configuration that isn't
rule_source="dynamic" + persistence_backend="postgres" (i.e. every
existing test and the default deployment stay byte-identical to before
Phase 5):

1. Automatic seeding (Settings.auto_seed_on_startup, default True) --
   SeedActivePolicyOnStartupUseCase: if no active rule pack exists yet
   under Settings.dynamic_rule_set_name, seed+activate the base fixture
   once. Never touches anything if one already exists -- "seed rules are
   used only during first deployment... never overwrite production data."
2. Cache warmup -- one deliberate PostgreSQL read (rule_repository.
   get_active()), which populates RuleCache's local L1 AND (if
   Settings.cache_backend="redis") writes through to the shared L2 Redis
   layer, so the very first real incident evaluation after startup is
   already served from a warm cache instead of paying a cold-load
   latency spike on whichever request happens to arrive first.

Failures in either step are logged as critical but never raise out of the
lifespan handler -- a database that's unreachable at boot must not crash
process startup (the "Never Crash" failure-strategy requirement extends
to boot, not just steady-state traffic); /health stays reachable, and the
incident-evaluation path will surface a clear error on its own until the
database recovers, rather than the whole process refusing to start."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _startup()
    yield
    # No shutdown steps today -- SQLAlchemy connection pools and the
    # redis-py client are both closed automatically by the process
    # exiting; listed here as the explicit place a future graceful-drain
    # step (e.g. "stop accepting new incidents, finish in-flight ones")
    # would go.


def _startup() -> None:
    from app.core.settings import get_settings
    settings = get_settings()

    if settings.persistence_backend != "postgres" or settings.rule_source != "dynamic":
        return  # nothing to seed or warm -- the static fixture composite needs neither

    from app.interfaces.api.dependencies import rule_pack_repository, rule_repository

    if settings.auto_seed_on_startup:
        try:
            from app.application.use_cases.seed_active_policy import SeedActivePolicyOnStartupUseCase
            result = SeedActivePolicyOnStartupUseCase(rule_pack_repository, settings.dynamic_rule_set_name).execute()
            if result.seeded:
                logger.info("Startup seed: created and activated %s v%s", result.pack_name, result.pack_version)
            else:
                logger.info("Startup seed: %s v%s already active -- nothing to do", result.pack_name, result.pack_version)
        except Exception:
            logger.critical(
                "Startup seeding failed -- the database may be unreachable. Continuing to start; "
                "POST /api/v1/incidents/evaluate will error until a rule pack is activated (manually "
                "via scripts/seed_base_rule_pack.py, POST /api/v1/rule-packs, or once the database recovers).",
                exc_info=True,
            )

    try:
        pack = rule_repository.get_active()
        logger.info("Startup cache warmup: active policy %s v%s (%d rules) warmed", pack.name, pack.version, len(pack.rules))
    except Exception:
        logger.critical(
            "Startup cache warmup failed -- no active rule pack could be loaded. "
            "POST /api/v1/incidents/evaluate will error until this is resolved.",
            exc_info=True,
        )
