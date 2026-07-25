# Persistence -- PostgreSQL, SQLAlchemy, Alembic

This is the first phase of the DecisioX enterprise buildout: real
persistence behind the repositories that were, until now, all in-memory.
It's additive by construction -- the default behavior is byte-for-byte
identical to before this phase, and every existing test proves it.

## What changed

`Settings.persistence_backend` (`app/core/settings.py`, read from `.env` /
environment variables) is `"memory"` by default. `app/interfaces/api/dependencies.py`
branches on it: `"memory"` constructs the same `InMemory*Repository` classes
that existed before this phase; `"postgres"` constructs SQLAlchemy-backed
equivalents implementing the *exact same domain interfaces*
(`DecisionRepository`, `RulePackRepository`, `ManualOverrideRepository`,
`EscalationRepository`, `EscalationPolicyRepository`, plus two new ones,
`AuditLogRepository` and `RequestLogRepository`). Nothing in `domain/` or
`application/` changed to make this possible -- that's the point of the
repository-pattern boundary this project has used from the start.

## Scope boundary -- what's deliberately NOT included

`rule_repository`, the hot incident-evaluation path (the
`CompositeRuleRepository` merging the base 35-rule pack with the six
additive rule packs, 142 rules total), is **not** switched by this setting.
It still reads from the in-memory JSON files, exactly as before. Moving it
to Postgres would mean: building a rule-authoring API, migrating 142 rules'
worth of JsonLogic conditions and actions into the `rules` table, and then
proving -- not assuming -- that Postgres-sourced evaluation produces
identical output to today's in-memory composite across every one of the 94
existing tests. That's real, valuable future work, but it's a materially
different risk profile than persisting decision history and audit trails,
and bundling it into this phase would have meant either rushing it or
stalling everything else behind it. `scripts/seed_base_rule_pack.py` seeds
the *base* 35-rule pack into Postgres so rule-pack lifecycle features
(versioning, activation, rollback) can be exercised against real data --
but the running API still evaluates incidents against the in-memory
composite regardless of `PERSISTENCE_BACKEND`.

## Schema

`app/infrastructure/db/models.py` maps 1:1 onto `app/infrastructure/database/schema.sql`,
which was designed at the very start of this project and already covered
nearly everything the enterprise spec's entity list asks for:

| Spec entity | This project |
|---|---|
| Rule | `RuleORM` |
| RuleVersion | `RuleSetORM` -- a "rule set" already *is* a version (draft/validated/shadow/active/deprecated/rolled_back, with `parent_version_id` for rollback lineage) |
| Decision | `DecisionORM` |
| DecisionAudit | `AuditLogORM` filtered to `entity_type='decision'` -- one general-purpose audit table, not a second table duplicating its shape |
| EvaluationHistory | `DecisionORM` rows, append-only per `incident_id` -- the full history already exists, it doesn't need a separate table |
| AuditLog | `AuditLogORM` |
| RequestLog | `RequestLogORM` -- genuinely new, `schema.sql` had no HTTP-request-level logging table |
| User / Role / Permission / APIKey | Added in Phase 2, alongside the auth feature work that reads/writes them -- see docs/auth.md |
| Simulation | Deliberately not added yet -- belongs with the simulation (Phase 4) feature work that will actually read/write it |

### Soft delete and optimistic locking

Applied only to `RuleSetORM` and `RuleORM` (`deleted_at`, `lock_version`
via `app/infrastructure/db/base.py`'s mixins) -- the two entities genuinely
edited in place over their lifetime. `decisions`, `audit_log`,
`manual_overrides`, `escalation_events` are append-only / immutable by
design (this project's own stated philosophy from the very first design
doc: an override or audit entry is a new record, never a mutation of an
old one). Applying soft-delete/optimistic-locking columns there regardless
would be cargo-culting a generic requirement onto entities it doesn't fit,
not engineering to it.

### Cross-dialect JSONB/UUID

Every JSONB and UUID column is declared with SQLAlchemy's `.with_variant()`:
Postgres gets the real, GIN-indexable `JSONB`/native `UUID` types (see the
Alembic migration, which uses `postgresql.JSONB`/`postgresql.UUID`
explicitly); SQLite -- used only in tests, since no live Postgres is
available in this sandbox -- gets a plain `JSON` column and a
`TypeDecorator` that stores UUIDs as 36-char strings. Same ORM models,
same queries, only the dialect changes. `tests/test_postgres_repositories.py`
proves every repository round-trips correctly this way.

## Running it

```bash
# 1. Start Postgres (via Docker, or point DATABASE_URL at an existing instance)
./docker-run.sh --detach          # starts db + api together, api waits for db's healthcheck

# 2. Run migrations (not automatic on container start -- see docker-compose.yml's
#    comment on why: auto-migrating on boot is a common source of production
#    incidents when multiple replicas race to migrate at once)
docker compose run --rm api alembic upgrade head

# 3. Seed reference data
docker compose run --rm api python scripts/seed_escalation_policies.py
docker compose run --rm api python scripts/seed_base_rule_pack.py
```

Or locally without Docker: set `PERSISTENCE_BACKEND=postgres` and
`DATABASE_URL` in `.env`, then `alembic upgrade head` and the two seed
scripts, same as above without the `docker compose run --rm api` prefix.

## Verification performed

- Full regression suite (`pytest tests/ -q`): 94 passed (85 prior + 9 new
  Postgres-repository round-trip tests), zero failures, zero changes to
  any pre-existing test file. The default (`memory`) backend is what every
  existing test still exercises -- this phase couldn't have broken them
  even in principle.
- `dependencies.py` exercised directly with `PERSISTENCE_BACKEND=postgres`
  (pointed at a throwaway SQLite file standing in for Postgres) end to
  end: repository classes resolve to the Postgres-backed implementations,
  a rule pack saves/activates correctly, a decision saves and its history
  round-trips.
- The Alembic migration was verified with `alembic upgrade head --sql`
  (offline mode -- renders the exact DDL Postgres would receive without
  needing a live connection) and inspected for correctness: correct
  `JSONB`/`UUID`/`ARRAY` types, correct indexes (including the two GIN
  indexes on `rules.conditions`/`rules.actions`), correct foreign keys and
  unique constraints, matching `schema.sql` and `models.py` exactly.
- No live Postgres was available in this environment to run the migration
  against a real database -- flagged honestly rather than claimed as fully
  verified. The offline-SQL check plus the SQLite-substitution round-trip
  tests are strong but not equivalent to running it for real; do that
  before trusting this in a real deployment.
