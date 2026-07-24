"""Central configuration, read from environment variables (and a local
.env file via python-dotenv/pydantic-settings) -- per the DecisioX spec's
"support development/test/staging/production, use environment validation"
requirement. Every field has a safe default so the app runs with zero
configuration (in-memory backend, stub AI provider); opting into Postgres
or a real AI provider is additive, done entirely via env vars.

Nothing in dependencies.py or elsewhere should read os.environ directly --
this is the one place configuration is parsed and validated, so it's the
one place that needs to change if a new setting is added."""

from functools import lru_cache
from typing import Literal, Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: Literal["development", "test", "staging", "production"] = "development"

    # -- Persistence -------------------------------------------------
    # "memory" (default) preserves the exact behavior every existing test
    # and the whole rest of this codebase was built and verified against.
    # "postgres" swaps every repository in dependencies.py for a
    # SQLAlchemy-backed implementation of the SAME interface -- no domain
    # or application code changes either way.
    persistence_backend: Literal["memory", "postgres"] = "memory"
    database_url: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/decisiox"
    database_pool_size: int = 5
    database_max_overflow: int = 10
    database_echo: bool = False

    # -- Rule source (dynamic Rule Management platform, docs/rule-management.md) --
    # "static" (default): the hot evaluation path reads the fixed, in-memory
    #   composite of 142 fixture rules across 7 packs -- exactly today's
    #   behavior, what every pre-existing test runs against.
    # "dynamic": the hot path reads through DynamicRuleRepository, a
    #   cache-fronted PostgresRuleRepository -- rules/rule packs created,
    #   published, activated, and rolled back via /api/v1/rules and
    #   /api/v1/rule-packs become live without an application restart.
    #   Requires persistence_backend="postgres".
    rule_source: Literal["static", "dynamic"] = "static"
    rule_cache_ttl_seconds: float = 10.0
    # The rule_sets.name the dynamic hot path treats as authoritative --
    # create/publish/activate a rule pack under this exact name via
    # /api/v1/rule-packs for it to actually serve incident evaluations.
    dynamic_rule_set_name: str = "noc-default"

    # -- AI provider ---------------------------------------------------
    # Strategy/factory pattern (app/ai/): "openai_compatible" works against
    # ANY OpenAI-compatible chat-completions endpoint, including a local
    # Ollama/llama.cpp server -- set ai_base_url to that server and
    # ai_api_key to anything non-empty (most local servers ignore it).
    # Swapping to real OpenAI/Gemini later is an env-var change only.
    ai_provider: Literal["stub", "openai_compatible", "gemini_compatible"] = "stub"
    ai_base_url: str = "http://localhost:11434/v1"   # Ollama's default OpenAI-compatible endpoint
    ai_api_key: str = "local-not-required"
    ai_model: str = "llama3"
    ai_timeout_seconds: float = 30.0

    # -- Auth (Phase 2) --------------------------------------------------
    jwt_secret: str = "dev-only-insecure-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_token_minutes: int = 15
    jwt_refresh_token_days: int = 7
    auth_required: bool = False  # additive: existing unauthenticated flow keeps working until explicitly enabled

    # -- Distributed policy cache platform (Phase 5, docs/policy-platform.md) --
    # "memory" (default): RuleCache's local, in-process TTLCache is the
    #   only layer -- exactly today's behavior, zero setup, what every
    #   pre-existing test runs against. Each app instance/replica warms and
    #   refreshes its own copy independently (push-invalidated via
    #   CacheRefreshNotifier, same as always).
    # "redis": adds a shared, distributed L2 layer in front of Postgres --
    #   Decision Engine -> local TTLCache (L1) -> Redis (L2, shared across
    #   every replica) -> Postgres (L3, fallback only). A cache refresh on
    #   any one replica warms Redis for every other replica too, not just
    #   itself. Requires rule_source="dynamic" and persistence_backend="postgres".
    cache_backend: Literal["memory", "redis"] = "memory"
    redis_url: str = "redis://localhost:6379/0"
    redis_socket_timeout_seconds: float = 2.0
    redis_key_prefix: str = "decisiox:rulecache"
    # How long a warmed Redis snapshot is trusted as a "last known good"
    # fallback if Postgres becomes unreachable (see RuleCache's failure
    # strategy docstring) -- deliberately much longer than
    # rule_cache_ttl_seconds, since it's a break-glass fallback, not the
    # normal refresh path.
    redis_snapshot_max_age_seconds: float = 3600.0

    # Automatic empty-database seeding on startup (only relevant when
    # rule_source="dynamic" + persistence_backend="postgres"): if no
    # active rule pack named dynamic_rule_set_name exists yet, seed it
    # from the fixture JSON, publish, and activate it -- once, and only
    # if the database is genuinely empty of it. Never overwrites existing
    # production data; disable if you want to seed explicitly via
    # scripts/seed_base_rule_pack.py instead.
    auto_seed_on_startup: bool = True

    # -- Simulation + bulk evaluation (Phase 4) ---------------------------
    # Safety caps, not feature switches -- both endpoints work identically
    # below these limits; above them they return a 422 rather than letting
    # an unbounded request run for an unbounded time. Generous enough for
    # "thousands of requests" (the roadmap's own phrasing) while still
    # being a real bound.
    bulk_evaluate_max_items: int = 2000
    simulation_max_compare_incidents: int = 200

    # -- Rate limiting (Phase 2) -----------------------------------------
    # Disabled by default so the existing test suite (which fires many
    # requests back-to-back against a single TestClient) is never affected
    # unless an operator opts in.
    rate_limit_enabled: bool = False
    rate_limit_requests_per_minute: int = 120

    # -- Misc --------------------------------------------------------
    log_level: str = "INFO"
    cors_allow_origins: str = "*"


@lru_cache
def get_settings() -> Settings:
    return Settings()
