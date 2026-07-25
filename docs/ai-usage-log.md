# AI Usage Log

Structured, per-interaction record of AI-assisted work on this project
(companion to the narrative [`AI_ENGINEERING_LOG.md`](AI_ENGINEERING_LOG.md),
which explains the *design reasoning*; this file is the append-only
*what/when/who* audit trail). Entries below cover the build sprint from
2026-07-24 15:00 UTC through 2026-07-25, across all four contributors.
From this point on, new entries are appended automatically by
[`app/infrastructure/ai/usage_logger.py`](../app/infrastructure/ai/usage_logger.py):

- Every real `AIProvider.generate_rule` / `document_rule` / `explain_decision`
  call is logged automatically when `AI_USAGE_LOG_ENABLED=true` (off by
  default — see `Settings.ai_usage_log_enabled`).
- `log_ai_entry(...)` in the same module can be called manually by any
  contributor to log an AI-assisted coding session, the same way the entries
  below were produced.

**Contributors:**
- Shivani Gulati <shivani.gulati77@gmail.com> — Core Decision Engine & Domain Model
- Tamanna Agnihotri <tamannaa.agnihotri@gmail.com> — Persistence, Auth & Security
- Shubham Kumar <kshubhamsharma464@gmail.com> — Rule Management Platform, Cache & Simulation
- Yaman Chowdhary <ychowdhary1@gmail.com> — AI Integration, API Layer & DevOps

---

### Entry #1 — Project scaffold
- *Timestamp / author:* 2026-07-24 15:00 UTC — Yaman Chowdhary <ychowdhary1@gmail.com>
- *AI tool + model:* Claude Code (Anthropic) — model: claude-sonnet-4-5
- *Task / module:* `README.md`, `requirements.txt`, `.gitignore`, minimal `app/main.py` stub
- *Prompt (verbatim):*
  > hey can u scaffold the repo for me - fastapi service, need requirements.txt (fastapi/uvicorn/pydantic/pytest/httpx/sqlalchemy/alembic/redis), gitignore for pycache/venv/.env and a placeholder main.py that just boots for now, nothing wired yet. rest of us gonna build on top of this tonite
- *AI output summary:* Generated `requirements.txt`, `.gitignore`, and a minimal `FastAPI()` app instance with no routers wired yet.
- *Decision:* Accepted as-is
- *If modified/rejected, why:* n/a
- *How it was validated:* `uvicorn app.main:app` boots without error.
- *Bugs found (if any) and resolution:* None.

---

### Entry #2 — Domain entities (Decision, Incident, Rule, RulePack)
- *Timestamp / author:* 2026-07-24 15:20 UTC — Shivani Gulati <shivani.gulati77@gmail.com>
- *AI tool + model:* Claude Code (Anthropic) — model: claude-opus-4-5
- *Task / module:* `app/domain/entities/*`, `app/domain/value_objects/rule_condition.py`
- *Prompt (verbatim):*
  > ok lets start w domain entities - Decision, Incident, Rule, RulePack, plus a coupla supporting ones (Escalation, ManualOverride). keep these as plain dataclasses, no framework imports at all pls, this layer needs to stay independant since everyone else builds infra on top of it. also need a RuleCondition value object for one jsonlogic style condition node
- *AI output summary:* Dataclass entities under `app/domain/entities/`, plus `RuleCondition` value object with `field`/`operator`/`value` and nested-condition support for `and`/`or`/`not`.
- *Decision:* Accepted as-is
- *If modified/rejected, why:* n/a
- *How it was validated:* Entities instantiate with no import errors when `app/interfaces` and `app/infrastructure` are excluded from the import graph.
- *Bugs found (if any) and resolution:* None.

---

### Entry #3 — Postgres schema.sql
- *Timestamp / author:* 2026-07-24 15:35 UTC — Tamanna Agnihotri <tamannaa.agnihotri@gmail.com>
- *AI tool + model:* Claude Code (Anthropic) — model: claude-opus-4-5
- *Task / module:* `app/infrastructure/database/schema.sql`
- *Prompt (verbatim):*
  > can u write the raw postgres schema for this thing - incidents, decisions, rules, rule_sets (rule packs), escalations, users, roles, permissions, api_keys, audit_log, request_log. add fks where it makes sense n index whatever columns the hot path is gonna filter on (incident status, decision incident_id, rule_sets.status)
- *AI output summary:* Full `CREATE TABLE` set with FKs and indexes, reference schema the SQLAlchemy models and Alembic migration are generated from.
- *Decision:* Accepted as-is
- *If modified/rejected, why:* n/a
- *How it was validated:* Schema reviewed against the domain entities field-by-field; loaded into a scratch Postgres instance and inspected with `\d`.
- *Bugs found (if any) and resolution:* None.

---

### Entry #4 — Domain interfaces (repository + service abstractions)
- *Timestamp / author:* 2026-07-24 16:10 UTC — Shivani Gulati <shivani.gulati77@gmail.com>
- *AI tool + model:* Claude Code (Anthropic) — model: claude-opus-4-5
- *Task / module:* `app/domain/interfaces/*`
- *Prompt (verbatim):*
  > need abstract repo interfaces (ABC) for every entity that needs persistance - incident, decision, rule, rule pack, escalation, user, role, permission, api key, audit log, request log. plus a CacheRefreshNotifier and a ContextProvider interface. just method signatures no implementation, tamanna n shubham are gonna build in-memory + postgres versions against these tonite
- *AI output summary:* One ABC per interface file under `app/domain/interfaces/`, CRUD-shaped method signatures matching each entity's identity field.
- *Decision:* Accepted as-is
- *If modified/rejected, why:* n/a
- *How it was validated:* Reviewed with Tamanna and Shubham before either started implementing against them, to avoid rework.
- *Bugs found (if any) and resolution:* None.

---

### Entry #5 — SQLAlchemy models.py
- *Timestamp / author:* 2026-07-24 16:25 UTC — Tamanna Agnihotri <tamannaa.agnihotri@gmail.com>
- *AI tool + model:* Claude Code (Anthropic) — model: claude-sonnet-4-5
- *Task / module:* `app/infrastructure/db/models.py`
- *Prompt (verbatim):*
  > translate the schema.sql into sqlalchemy 2.0 declarative models pls, one class per table, relationships wherever the schema has fks. keep it strictly in the infra layer tho, domain entities should never import from here
- *AI output summary:* Declarative model classes mirroring `schema.sql`, with `relationship()` on the FK-linked tables.
- *Decision:* Accepted as-is
- *If modified/rejected, why:* n/a
- *How it was validated:* `Base.metadata.create_all()` against a scratch SQLite DB as a quick structural smoke test before wiring real Postgres.
- *Bugs found (if any) and resolution:* None.

---

### Entry #6 — risk_scorer.py + confidence_calculator.py
- *Timestamp / author:* 2026-07-24 16:50 UTC — Shivani Gulati <shivani.gulati77@gmail.com>
- *AI tool + model:* Claude Code (Anthropic) — model: claude-sonnet-4-5
- *Task / module:* `app/domain/services/risk_scorer.py`, `confidence_calculator.py`
- *Prompt (verbatim):*
  > need risk_scorer that computes a 0-100 risk score from the matched rules weights, and confidence_calculator that shows how many optional context fields were actually present vs expected for the matched rules. pls document the formula in a docstring so its not a mystery later
- *AI output summary:* Weighted-sum risk score with normalization; `confidence = present_fields / expected_fields`.
- *Decision:* Modified
- *If modified/rejected, why:* The confidence formula could exceed 1.0 when extra, unexpected context fields were present. Clamped to `[0, 1]`.
- *How it was validated:* `tests/test_context_aggregation.py` boundary cases (zero fields, all fields present, extra fields).
- *Bugs found (if any) and resolution:* Division-by-zero when a rule pack declared no expected context fields — guarded with a fallback confidence of `1.0`.

---

### Entry #7 — db/mappers.py + db/base.py
- *Timestamp / author:* 2026-07-24 17:05 UTC — Tamanna Agnihotri <tamannaa.agnihotri@gmail.com>
- *AI tool + model:* Claude Code (Anthropic) — model: claude-sonnet-4-5
- *Task / module:* `app/infrastructure/db/mappers.py`, `app/infrastructure/db/base.py`
- *Prompt (verbatim):*
  > write mapper functions between sqlalchemy rows and domain entities, both directions, plus a base.py w the engine/sessionmaker setup driven off Settings.database_url/pool_size/max_overflow
- *AI output summary:* `*_to_entity()` / `*_to_model()` mapper pairs per table, plus `get_engine()`/`get_session()` in `base.py`.
- *Decision:* Accepted as-is
- *If modified/rejected, why:* n/a
- *How it was validated:* Round-trip test — entity → model → entity produces an identical entity.
- *Bugs found (if any) and resolution:* None.

---

### Entry #8 — conflict_resolver.py + compliance_applier.py
- *Timestamp / author:* 2026-07-24 17:30 UTC — Shivani Gulati <shivani.gulati77@gmail.com>
- *AI tool + model:* Claude Code (Anthropic) — model: claude-sonnet-4-5
- *Task / module:* `app/domain/services/conflict_resolver.py`, `compliance_applier.py`
- *Prompt (verbatim):*
  > when more than one rule in a pack matches the same incident, need to resolve conflicting actions by rule priority, then most-restrictive-wins as a tiebreak. and it should show which rules got suppressed n why. also separately compliance_applier should apply whatever regulatory-required actions gotta always fire no matter what the rules said
- *AI output summary:* `ConflictResolver` comparing `rule.priority` with a suppressed-rules trail; `ComplianceApplier` appending mandatory actions post-resolution.
- *Decision:* Accepted as-is
- *If modified/rejected, why:* n/a
- *How it was validated:* Unit tests with three overlapping rules at different priority levels, plus a compliance-mandatory-action fixture.
- *Bugs found (if any) and resolution:* None.

---

### Entry #9 — migrations/ (Alembic)
- *Timestamp / author:* 2026-07-24 17:45 UTC — Tamanna Agnihotri <tamannaa.agnihotri@gmail.com>
- *AI tool + model:* Claude Code (Anthropic) — model: claude-sonnet-4-5
- *Task / module:* `migrations/`, `alembic.ini`
- *Prompt (verbatim):*
  > init alembic against the models.py metadata and generate the first migration from schema.sql. env.py should read DATABASE_URL off Settings not some hardcoded value pls
- *AI output summary:* `alembic.ini`, `migrations/env.py` wired to `Settings.database_url`, and an autogenerated initial revision.
- *Decision:* Modified
- *If modified/rejected, why:* Autogenerate initially missed the indexes defined in `schema.sql` (Alembic's autogenerate doesn't diff index definitions as reliably as columns) — added them explicitly to the revision.
- *How it was validated:* `alembic upgrade head` against a scratch Postgres container, `\d` compared against `schema.sql`.
- *Bugs found (if any) and resolution:* As above (missing indexes in autogenerated revision) — added manually.

---

### Entry #10 — explainability_builder.py + execution_plan_builder.py + context_aggregation_service.py
- *Timestamp / author:* 2026-07-24 18:10 UTC — Shivani Gulati <shivani.gulati77@gmail.com>
- *AI tool + model:* Claude Code (Anthropic) — model: claude-opus-4-5
- *Task / module:* `app/domain/services/explainability_builder.py`, `execution_plan_builder.py`, `context_aggregation_service.py`
- *Prompt (verbatim):*
  > need 3 services: explainability_builder - deterministic explanation string for a Decision, zero ai involved; execution_plan_builder - turns a Decisions actions into an ordered idempotent execution plan; context_aggregation_service - merges incident payload fields w whatever the ContextProvider impls return into one context dict for the engine to use
- *AI output summary:* Template-based explanation builder; execution plan as an ordered list of `ExecutionStep`; context aggregator merging incident fields with provider results, incident fields winning on key collision.
- *Decision:* Accepted as-is
- *If modified/rejected, why:* n/a
- *How it was validated:* Snapshot tests against fixture incidents for each of the three services.
- *Bugs found (if any) and resolution:* None.

---

### Entry #11 — core/security.py
- *Timestamp / author:* 2026-07-24 18:25 UTC — Tamanna Agnihotri <tamannaa.agnihotri@gmail.com>
- *AI tool + model:* Claude Code (Anthropic) — model: claude-opus-4-5
- *Task / module:* `app/core/security.py`
- *Prompt (verbatim):*
  > need jwt helpers - issue_access_token, issue_refresh_token, decode_token (should raise on expiry/bad sig/wrong token type) and bcrypt password hash/verify. access token 15 mins, refresh 7 days, both driven off Settings.jwt_*
- *AI output summary:* `security.py` with PyJWT-based issue/decode functions and `passlib`-style bcrypt hash/verify helpers.
- *Decision:* Modified
- *If modified/rejected, why:* `decode_token` initially didn't check the token's `type` claim, so a refresh token could be presented where an access token was expected. Added an explicit `token_type` check.
- *How it was validated:* `tests/test_security_core.py` — expired token, wrong secret, refresh-token-used-as-access-token cases.
- *Bugs found (if any) and resolution:* As above (refresh/access token confusion) — fixed and covered by a regression test.

---

### Entry #12 — Repository interfaces for rule/decision/incident/escalation
- *Timestamp / author:* 2026-07-24 18:50 UTC — Shubham Kumar <kshubhamsharma464@gmail.com>
- *AI tool + model:* Claude Code (Anthropic) — model: claude-sonnet-4-5
- *Task / module:* `app/domain/interfaces/rule_pack_repository.py`, `decision_repository.py`, `incident_repository.py`, `escalation_repository.py`, `escalation_policy_repository.py`
- *Prompt (verbatim):*
  > shivanis base interfaces cover crud, i need to extend the rule-pack n decision repo interfaces w lifecycle specific stuff - find_active_by_name, list_by_status for rule packs, find_by_incident_id for decisions. keep it abstract only for now, gonna implement next
- *AI output summary:* Extended interface methods added on top of the base CRUD set from Entry #4.
- *Decision:* Accepted as-is
- *If modified/rejected, why:* n/a
- *How it was validated:* Reviewed against the rule pack lifecycle design (draft/published/active/shadow) before implementing any concrete repo against it.
- *Bugs found (if any) and resolution:* None.

---

### Entry #13 — core/settings.py + core/cache.py
- *Timestamp / author:* 2026-07-24 19:05 UTC — Shivani Gulati <shivani.gulati77@gmail.com>
- *AI tool + model:* Claude Code (Anthropic) — model: claude-sonnet-4-5
- *Task / module:* `app/core/settings.py`, `app/core/cache.py`
- *Prompt (verbatim):*
  > need a central Settings(BaseSettings) that reads from .env, safe default for literally every field so app runs w zero config (in memory backend, stub ai provider). also a small local ttl cache primitive in core/cache.py that the rule cache is gonna build on top of later
- *AI output summary:* `Settings` class with persistence/rule-source/AI/auth/cache/rate-limit fields, all defaulted; `TTLCache` with `get`/`set`/`invalidate` and per-key expiry.
- *Decision:* Accepted as-is
- *If modified/rejected, why:* n/a
- *How it was validated:* App boots with no `.env` file present at all — every field falls back to its default.
- *Bugs found (if any) and resolution:* None.

---

### Entry #14 — In-memory auth repos
- *Timestamp / author:* 2026-07-24 19:20 UTC — Tamanna Agnihotri <tamannaa.agnihotri@gmail.com>
- *AI tool + model:* Claude Code (Anthropic) — model: claude-sonnet-4-5
- *Task / module:* `in_memory_user_repository.py`, `in_memory_role_repository.py`, `in_memory_permission_repository.py`, `in_memory_api_key_repository.py`, `in_memory_audit_log_repository.py`, `in_memory_request_log_repository.py`
- *Prompt (verbatim):*
  > need in memory impls of the auth side repo interfaces, dict backed, and seed viewer/operator/admin roles in-process so the app works w zero external services out the box
- *AI output summary:* Six repository classes, each a thin dict wrapper implementing its interface; role/permission seed data included.
- *Decision:* Accepted as-is
- *If modified/rejected, why:* n/a
- *How it was validated:* `tests/test_security_core.py` fixtures use these directly with no DB running.
- *Bugs found (if any) and resolution:* None.

---

### Entry #15 — Redis cache infrastructure
- *Timestamp / author:* 2026-07-24 19:45 UTC — Shubham Kumar <kshubhamsharma464@gmail.com>
- *AI tool + model:* Claude Code (Anthropic) — model: claude-opus-4-5
- *Task / module:* `app/infrastructure/cache/rule_cache.py`, `redis_cache_backend.py`, `in_memory_cache_refresh_notifier.py`, `rule_snapshot.py`
- *Prompt (verbatim):*
  > wanna design RuleCache as L1 (local ttl cache) with an optional L2 (redis, shared across replicas) infront of postgres. a cache refresh on any one replica should push-invalidate every other replicas L1 too, not just the one that triggered it. and if postgres goes unreachable, fall back to last known good redis snapshot for a bounded window
- *AI output summary:* `RuleCache` reading L1 → L2 (Redis) → L3 (Postgres); `RuleSnapshot` capturing a timestamped last-known-good copy; `CacheRefreshNotifier` publishing invalidation events through Redis pub/sub.
- *Decision:* Accepted as-is
- *If modified/rejected, why:* n/a
- *How it was validated:* Design walked through with the team before implementation; unit-testable pieces exercised with `fakeredis` (see Entry #19).
- *Bugs found (if any) and resolution:* None yet — deferred to integration testing once Postgres-backed repos exist.

---

### Entry #16 — engine/evaluator_factory.py + evaluators/
- *Timestamp / author:* 2026-07-24 20:00 UTC — Shivani Gulati <shivani.gulati77@gmail.com>
- *AI tool + model:* Claude Code (Anthropic) — model: claude-sonnet-4-5
- *Task / module:* `app/engine/evaluator_factory.py`, `app/engine/evaluators/{arithmetic,boolean,composite,membership,numeric,reference_lookup,base}.py`
- *Prompt (verbatim):*
  > need a jsonlogic style condition evaluator w pluggable operators - arithmetic, boolean, composite (and/or/not), membership (in/not_in), numeric comparisons, and reference_lookup for reading a field off context. use a factory/registry pattern so adding a new operator later doesnt mean touching the dispatcher
- *AI output summary:* `evaluator_factory.py` with an operator registry dict, one module per operator family.
- *Decision:* Modified
- *If modified/rejected, why:* The composite `not` evaluator initially required a list of exactly one condition to mirror `and`/`or`'s shape; the spec's own examples pass a single nested condition dict directly. Adjusted to accept both.
- *How it was validated:* `tests/test_policy_engine.py` and `tests/test_new_operators.py`, table-driven per operator.
- *Bugs found (if any) and resolution:* As above (composite `not` shape) — fixed, covered by a regression test.

---

### Entry #17 — Rejected: make Redis the default cache backend
- *Timestamp / author:* 2026-07-24 20:20 UTC — Shubham Kumar <kshubhamsharma464@gmail.com>
- *AI tool + model:* Claude Code (Anthropic) — model: claude-opus-4-5
- *Task / module:* `app/infrastructure/cache/rule_cache.py`, `app/core/settings.py`
- *Prompt (verbatim):*
  > since we're already building the redis L2 layer, should CACHE_BACKEND just default to "redis" instead of "memory" so new deployments get the distributed benifit outta the box? feels like a waste not to
- *AI output summary:* A variant of `Settings` with `cache_backend: Literal[...] = "redis"` as the default.
- *Decision:* Rejected
- *If modified/rejected, why:* Breaks the "zero setup" guarantee every existing and yet-to-be-written test depends on — a fresh checkout with no Redis running would fail to start. `cache_backend="memory"` stays the default; Redis is strictly opt-in via env var, same convention as `persistence_backend` and `ai_provider`.
- *How it was validated:* n/a — reverted before implementing.
- *Bugs found (if any) and resolution:* n/a.

---

### Entry #18 — Postgres auth repos
- *Timestamp / author:* 2026-07-24 20:40 UTC — Tamanna Agnihotri <tamannaa.agnihotri@gmail.com>
- *AI tool + model:* Claude Code (Anthropic) — model: claude-sonnet-4-5
- *Task / module:* `postgres_user_repository.py`, `postgres_role_repository.py`, `postgres_permission_repository.py`, `postgres_api_key_repository.py`, `postgres_audit_log_repository.py`, `postgres_request_log_repository.py`
- *Prompt (verbatim):*
  > need postgres backed impls of the same auth repo interfaces the in memory versions implement, using db/mappers.py n db/base.py's session. behavior gotta be identical to the in memory ones from the callers pov, dont wanna have to branch anywhere else in the code
- *AI output summary:* Six repository classes issuing SQLAlchemy queries through the shared session, mapped to/from entities via `mappers.py`.
- *Decision:* Accepted as-is
- *If modified/rejected, why:* n/a
- *How it was validated:* Same contract test suite run against both the in-memory and Postgres implementations via parametrized fixtures.
- *Bugs found (if any) and resolution:* None.

---

### Entry #19 — Postgres repos for rule/decision/incident/escalation
- *Timestamp / author:* 2026-07-24 21:00 UTC — Shubham Kumar <kshubhamsharma464@gmail.com>
- *AI tool + model:* Claude Code (Anthropic) — model: claude-sonnet-4-5
- *Task / module:* `postgres_rule_pack_repository.py`, `postgres_rule_repository.py`, `postgres_decision_repository.py`, `postgres_incident_repository.py`, `postgres_escalation_repository.py`, `postgres_escalation_policy_repository.py`
- *Prompt (verbatim):*
  > need postgres impls of the rule/decision/incident/escalation repo interfaces from earlier, built against tamanna's db/mappers.py and db/base.py session setup
- *AI output summary:* Six repository classes, rule-pack repo including the `find_active_by_name`/`list_by_status` lifecycle queries.
- *Decision:* Accepted as-is
- *If modified/rejected, why:* n/a
- *How it was validated:* `tests/test_postgres_repositories.py` run against a scratch Postgres container.
- *Bugs found (if any) and resolution:* None.

---

### Entry #20 — infrastructure/data/ 35-rule seed JSON
- *Timestamp / author:* 2026-07-24 21:20 UTC — Shivani Gulati <shivani.gulati77@gmail.com>
- *AI tool + model:* Claude Code (Anthropic) — model: claude-sonnet-4-5
- *Task / module:* `app/infrastructure/data/` (base rule pack fixture)
- *Prompt (verbatim):*
  > can u draft the seed rule pack - like 35 realistic noc/incident-response rules covering severity escalation, sla driven priority bumps and vendor outage handling. shape it exactly like CreateRuleRequest so it loads thru the same validation path as a human authored rule pack would
- *AI output summary:* JSON fixture of 35 rules with priorities, condition trees, and actions, grouped loosely by scenario family.
- *Decision:* Modified
- *If modified/rejected, why:* Four of the drafted rules had priority collisions with no tiebreak-relevant difference, which would make conflict-resolution behavior nondeterministic in tests. Adjusted priorities to be unique within each conflicting group.
- *How it was validated:* Loaded through `ValidateRuleUseCase` — zero validation errors; `tests/test_policy_engine.py` fixtures build on this set.
- *Bugs found (if any) and resolution:* As above (priority collisions) — fixed.

---

### Entry #21 — register_user.py
- *Timestamp / author:* 2026-07-24 21:40 UTC — Tamanna Agnihotri <tamannaa.agnihotri@gmail.com>
- *AI tool + model:* Claude Code (Anthropic) — model: claude-sonnet-4-5
- *Task / module:* `app/application/use_cases/register_user.py`
- *Prompt (verbatim):*
  > registration use case - hash the password thru core/security.py, default new users to "viewer" role, and reject duplicate emails w a proper domain level exception instead of letting a db constraint error just leak up to the caller
- *AI output summary:* `RegisterUserUseCase` checking `UserRepository.find_by_email` before insert, raising `DuplicateEmailError` on collision.
- *Decision:* Accepted as-is
- *If modified/rejected, why:* n/a
- *How it was validated:* Tests covering successful registration, duplicate email rejection, and default role assignment.
- *Bugs found (if any) and resolution:* None.

---

### Entry #22 — In-memory repos + composite_rule_repository + rule pack loaders
- *Timestamp / author:* 2026-07-24 22:00 UTC — Shubham Kumar <kshubhamsharma464@gmail.com>
- *AI tool + model:* Claude Code (Anthropic) — model: claude-sonnet-4-5
- *Task / module:* in-memory rule/decision/incident/escalation/manual-override repos, `composite_rule_repository.py`, `csr_sla_rule_pack_loader.py`, `historical_pattern_rule_pack_loader.py`, `industry_sop_rule_pack_loader.py`, `net_inf_rule_pack_loader.py`, `sla_rule_pack_loader.py`, `vast_rule_pack_loader.py`
- *Prompt (verbatim):*
  > need in memory repos matching the postgres ones, plus a CompositeRuleRepository that merges shivanis 35-rule seed pack w the extra specialized rule pack loaders (sla, historical pattern, industry sop, network infra, vendor assessment) into one queryable surface for the static rule_source mode
- *AI output summary:* In-memory repos, `CompositeRuleRepository` merging multiple `RulePackLoader` outputs by rule code, six loader classes each parsing their own fixture file.
- *Decision:* Modified
- *If modified/rejected, why:* Two loaders defined rules with the same `ruleCode` as the base seed pack, which `CompositeRuleRepository` silently let the later-loaded one overwrite. Changed to raise on duplicate rule codes at composition time instead of overwriting silently.
- *How it was validated:* `tests/test_composite_repository_backward_compat.py`, `test_csr_sla_rule_pack.py`, `test_historical_pattern_rule_pack.py`, `test_industry_sop_rule_pack.py`, `test_net_inf_rule_pack.py`, `test_sla_rule_pack.py`, `test_vast_rule_pack.py`.
- *Bugs found (if any) and resolution:* As above (silent rule-code collision) — fixed to raise explicitly.

---

### Entry #23 — application/orchestrator.py
- *Timestamp / author:* 2026-07-24 22:20 UTC — Shivani Gulati <shivani.gulati77@gmail.com>
- *AI tool + model:* Claude Code (Anthropic) — model: claude-opus-4-5
- *Task / module:* `app/application/orchestrator.py`
- *Prompt (verbatim):*
  > the orchestrator needs to tie the engine + all domain services together - aggregate context, evaluate rules, resolve conflicts, apply compliance actions, score risk/confidence, build the execution plan n explanation, then return a Decision. one method, clear step order, each step just delegating to its own service, no business logic inline in here pls
- *AI output summary:* `Orchestrator.decide(incident)` calling each domain service in sequence and assembling the final `Decision`.
- *Decision:* Accepted as-is
- *If modified/rejected, why:* n/a
- *How it was validated:* End-to-end fixture incidents run through the full pipeline, output compared against hand-computed expected decisions.
- *Bugs found (if any) and resolution:* None.

---

### Entry #24 — authenticate_user.py
- *Timestamp / author:* 2026-07-24 22:40 UTC — Tamanna Agnihotri <tamannaa.agnihotri@gmail.com>
- *AI tool + model:* Claude Code (Anthropic) — model: claude-sonnet-4-5
- *Task / module:* `app/application/use_cases/authenticate_user.py`
- *Prompt (verbatim):*
  > login use case - verify password against the stored hash, issue access+refresh token pair on success, generic "invalid credentials" error on failure (dont leak whether it was the email or password that was wrong). also need a refresh token exchange path
- *AI output summary:* `AuthenticateUserUseCase.login()` and `.refresh()`, both going through `core/security.py`.
- *Decision:* Accepted as-is
- *If modified/rejected, why:* n/a
- *How it was validated:* `tests/test_auth.py` — correct credentials, wrong password, unknown email (both return the same generic error), refresh flow.
- *Bugs found (if any) and resolution:* None.

---

### Entry #25 — Rejected: Redis-backed refresh-token revocation list
- *Timestamp / author:* 2026-07-24 23:00 UTC — Tamanna Agnihotri <tamannaa.agnihotri@gmail.com>
- *AI tool + model:* Claude Code (Anthropic) — model: claude-opus-4-5
- *Task / module:* `app/core/security.py`, `app/application/use_cases/authenticate_user.py`
- *Prompt (verbatim):*
  > for fast token revocation on logout, could we push each issued refresh tokens jti into redis w a ttl matching its expiry, n check membership on refresh? would make "log out everywhere" trivial too, seems easy
- *AI output summary:* A revocation-check variant of `authenticate_user.py`'s refresh path that queried a `RedisRevocationStore`.
- *Decision:* Rejected
- *If modified/rejected, why:* Would make core auth — something every request potentially depends on when `AUTH_REQUIRED=true` — hard-depend on Redis being reachable, contradicting the project's "auth works with zero external services by default" contract (Entry #14/#18's in-memory and Postgres repos are both meant to be sufficient on their own). Revocation is deferred to a Postgres-backed used-token table instead, consistent with whichever persistence backend is already configured.
- *How it was validated:* n/a — reverted before merging.
- *Bugs found (if any) and resolution:* n/a.

---

### Entry #26 — rule_pack_lifecycle.py
- *Timestamp / author:* 2026-07-24 23:20 UTC — Shubham Kumar <kshubhamsharma464@gmail.com>
- *AI tool + model:* Claude Code (Anthropic) — model: claude-opus-4-5
- *Task / module:* `app/application/use_cases/rule_pack_lifecycle.py`
- *Prompt (verbatim):*
  > implement the rule pack lifecycle - draft, published, active, w a shadow stage that evaluates incidents without touching production decisions. gate transitions w rules:publish / rules:activate permissions n only allow valid transitions (draft->published->active, no skipping a stage)
- *AI output summary:* State machine enforcing the valid transition graph, raising a domain exception on an illegal transition.
- *Decision:* Accepted as-is
- *If modified/rejected, why:* n/a
- *How it was validated:* `tests/test_rule_pack_lifecycle.py` — illegal transitions (e.g. draft → active) assert a `409`.
- *Bugs found (if any) and resolution:* None.

---

### Entry #27 — evaluate_incident.py
- *Timestamp / author:* 2026-07-24 23:40 UTC — Shivani Gulati <shivani.gulati77@gmail.com>
- *AI tool + model:* Claude Code (Anthropic) — model: claude-sonnet-4-5
- *Task / module:* `app/application/use_cases/evaluate_incident.py`
- *Prompt (verbatim):*
  > EvaluateIncidentUseCase - take an incident payload, run it thru the orchestrator, persist the resulting Decision via DecisionRepository, then return it. this is the hot path so no unneccesary allocation or repeated context lookups pls
- *AI output summary:* Thin use case wrapping `Orchestrator.decide()` plus a single `DecisionRepository.save()` call.
- *Decision:* Accepted as-is
- *If modified/rejected, why:* n/a
- *How it was validated:* Integration test asserting the persisted decision matches what the orchestrator returned.
- *Bugs found (if any) and resolution:* None.

---

### Entry #28 — create_api_key.py
- *Timestamp / author:* 2026-07-25 00:00 UTC — Tamanna Agnihotri <tamannaa.agnihotri@gmail.com>
- *AI tool + model:* Claude Code (Anthropic) — model: claude-sonnet-4-5
- *Task / module:* `app/application/use_cases/create_api_key.py`
- *Prompt (verbatim):*
  > need service-to-service api keys as an alt to jwt - hashed at rest, scoped to same permission set as user roles, revocable. should return the raw key exactly once at creation time only
- *AI output summary:* `CreateApiKeyUseCase` returning the raw key in the response only, storing its hash via `ApiKeyRepository`.
- *Decision:* Accepted as-is
- *If modified/rejected, why:* n/a
- *How it was validated:* Test asserting the raw key never appears in any repository state or log line after creation.
- *Bugs found (if any) and resolution:* None.

---

### Entry #29 — rollback_rule_pack.py + promote_to_shadow.py
- *Timestamp / author:* 2026-07-25 00:20 UTC — Shubham Kumar <kshubhamsharma464@gmail.com>
- *AI tool + model:* Claude Code (Anthropic) — model: claude-sonnet-4-5
- *Task / module:* `app/application/use_cases/rollback_rule_pack.py`, `promote_to_shadow.py`
- *Prompt (verbatim):*
  > rollback_rule_pack should revert to a previous active pack. promote_to_shadow should put a published pack into shadow mode so it evaluates alongside the active pack w/o touching real decisions
- *AI output summary:* Rollback and shadow-promotion use cases built on the lifecycle state machine from Entry #26.
- *Decision:* Modified
- *If modified/rejected, why:* Rollback initially allowed targeting a pack that was still in `draft` state, which doesn't correspond to a real prior production state. Restricted rollback targets to packs that were previously `active`.
- *How it was validated:* `tests/test_rule_pack_lifecycle.py` covers the invalid-rollback-target case.
- *Bugs found (if any) and resolution:* As above — fixed.

---

### Entry #30 — conftest.py / pytest.ini + engine test scaffolding
- *Timestamp / author:* 2026-07-25 00:40 UTC — Shivani Gulati <shivani.gulati77@gmail.com>
- *AI tool + model:* Claude Code (Anthropic) — model: claude-sonnet-4-5
- *Task / module:* `conftest.py`, `pytest.ini`, `tests/conftest.py`
- *Prompt (verbatim):*
  > need pytest.ini w pythonpath = . so tests can import app/ without installing it, plus conftest.py fixtures for a fresh in memory rule repo, a use-case-under-test helper, and a sample incident payload (inc_101) the engine tests can all reuse instead of copy pasting fixtures everywhere
- *AI output summary:* Root `pytest.ini`, `tests/conftest.py` with `rule_repo`, `use_case`, and `inc_101_payload` fixtures.
- *Decision:* Accepted as-is
- *If modified/rejected, why:* n/a
- *How it was validated:* Every subsequent test file in the suite imports these fixtures successfully.
- *Bugs found (if any) and resolution:* None.

---

### Entry #31 — auth_router.py + interfaces/api/security.py + middleware/
- *Timestamp / author:* 2026-07-25 01:00 UTC — Tamanna Agnihotri <tamannaa.agnihotri@gmail.com>
- *AI tool + model:* Claude Code (Anthropic) — model: claude-sonnet-4-5
- *Task / module:* `app/interfaces/api/auth_router.py`, `app/interfaces/api/security.py`, `app/interfaces/api/middleware/rate_limit.py`, `security_headers.py`
- *Prompt (verbatim):*
  > need /auth/login, /auth/refresh, /auth/register endpoints. also a require_permission() fastapi dependency that 403s on missing rbac permission. rate limiting middleware should be off by default via RATE_LIMIT_ENABLED, but security headers middleware always on regardless
- *AI output summary:* `auth_router.py` wiring the use cases from Entries #21/#24/#28; `security.py`'s `require_permission()` dependency factory; token-bucket rate limiter; fixed security-header set.
- *Decision:* Accepted as-is
- *If modified/rejected, why:* n/a
- *How it was validated:* `tests/test_middleware.py` with the rate limiter explicitly enabled via a settings override (kept off for every other test file).
- *Bugs found (if any) and resolution:* None.

---

### Entry #32 — simulate_rules.py + replay_simulation.py
- *Timestamp / author:* 2026-07-25 01:20 UTC — Shubham Kumar <kshubhamsharma464@gmail.com>
- *AI tool + model:* Claude Code (Anthropic) — model: claude-sonnet-4-5
- *Task / module:* `app/application/use_cases/simulate_rules.py`, `replay_simulation.py`
- *Prompt (verbatim):*
  > simulate_rules should run a draft or shadow rule pack against a batch of sample incidents, capped at SIMULATION_MAX_COMPARE_INCIDENTS. replay_simulation should re-run a past incident batch against whatever pack is currently active, for regression comparison
- *AI output summary:* Both use cases reusing `Orchestrator.decide()` per incident against the specified pack, without persisting decisions.
- *Decision:* Accepted as-is
- *If modified/rejected, why:* n/a
- *How it was validated:* Tests with a payload one item over the cap asserting `422`, within-cap payload asserting correct per-incident results.
- *Bugs found (if any) and resolution:* None.

---

### Entry #33 — Engine test bundle
- *Timestamp / author:* 2026-07-25 01:40 UTC — Shivani Gulati <shivani.gulati77@gmail.com>
- *AI tool + model:* Claude Code (Anthropic) — model: claude-sonnet-4-5
- *Task / module:* `tests/test_conflict_resolver.py`, `test_policy_engine.py`, `test_execution_plan.py`, `test_context_aggregation.py`, `test_compliance.py`, `test_new_operators.py`
- *Prompt (verbatim):*
  > need full test coverage for the engine n domain services layer - every operator, conflict resolution w 2-3 overlapping rules, execution plan ordering, context aggregation merge precedence, compliance mandatory-action injection. basically dont wanna ship this w gaps
- *AI output summary:* Table-driven test suites across the six files, using the `rule_repo`/`inc_101_payload` fixtures from Entry #30.
- *Decision:* Accepted as-is
- *If modified/rejected, why:* n/a
- *How it was validated:* All six files run green locally before commit.
- *Bugs found (if any) and resolution:* None beyond what was already fixed in Entries #6, #16, #20.

---

### Entry #34 — Auth/security test bundle
- *Timestamp / author:* 2026-07-25 02:00 UTC — Tamanna Agnihotri <tamannaa.agnihotri@gmail.com>
- *AI tool + model:* Claude Code (Anthropic) — model: claude-sonnet-4-5
- *Task / module:* `tests/test_auth.py`, `test_postgres_repositories.py`, `test_security_core.py`, `test_middleware.py`
- *Prompt (verbatim):*
  > lets round out test coverage for the whole persistence/auth layer - login/refresh/register flows, rbac permission matrix per role, postgres repo contract tests (same suite as the in memory repos get), rate-limit n security-header middleware behavior
- *AI output summary:* Four test files covering the full auth stack end to end.
- *Decision:* Accepted as-is
- *If modified/rejected, why:* n/a
- *How it was validated:* Full run against both `PERSISTENCE_BACKEND=memory` and a scratch Postgres container.
- *Bugs found (if any) and resolution:* None beyond what was already fixed in Entries #9, #11, #18.

---

### Entry #35 — compare_rule_packs.py + decision_distribution.py
- *Timestamp / author:* 2026-07-25 02:20 UTC — Shubham Kumar <kshubhamsharma464@gmail.com>
- *AI tool + model:* Claude Code (Anthropic) — model: claude-sonnet-4-5
- *Task / module:* `app/application/use_cases/compare_rule_packs.py`, `decision_distribution.py`
- *Prompt (verbatim):*
  > compare_rule_packs should diff two rule packs effective decisions across the same incident batch, show which incidents changed outcome. decision_distribution should aggregate a batch of decisions into counts by outcome/priority/risk-band for the simulation summary
- *AI output summary:* `compare_rule_packs.py` producing a per-incident diff list; `decision_distribution.py` producing aggregate counts consumed by `simulate_rules.py`.
- *Decision:* Modified
- *If modified/rejected, why:* The distribution counts initially double-counted an incident when it matched multiple rules within the same pack. Changed to count by final decision outcome, not by individual rule match.
- *How it was validated:* `tests/test_simulation_api.py` asserting correct aggregate counts against a fixture batch with known overlaps.
- *Bugs found (if any) and resolution:* As above (double-counting) — fixed.

---

### Entry #36 — docs: decision-engine-design.md + tradeoffs.md
- *Timestamp / author:* 2026-07-25 02:40 UTC — Shivani Gulati <shivani.gulati77@gmail.com>
- *AI tool + model:* Claude Code (Anthropic) — model: claude-sonnet-4-5
- *Task / module:* `docs/decision-engine-design.md`, `docs/tradeoffs.md`
- *Prompt (verbatim):*
  > write up the decision engines design pls - entity model, evaluator/operator registry, conflict resolution n compliance layering, risk/confidence scoring, orchestrator flow. n separately a tradeoffs.md documenting the deliberate simplifications we made (like static in memory rule composite as the default) n what upgrading each one actually looks like
- *AI output summary:* Two design docs describing the engine layer and the tradeoffs made to ship it in this sprint.
- *Decision:* Accepted as-is
- *If modified/rejected, why:* n/a
- *How it was validated:* Reviewed against the actual implementation for drift before committing.
- *Bugs found (if any) and resolution:* None.

---

### Entry #37 — docs: auth.md + persistence.md
- *Timestamp / author:* 2026-07-25 03:00 UTC — Tamanna Agnihotri <tamannaa.agnihotri@gmail.com>
- *AI tool + model:* Claude Code (Anthropic) — model: claude-sonnet-4-5
- *Task / module:* `docs/auth.md`, `docs/persistence.md`
- *Prompt (verbatim):*
  > document the auth model (jwt + api keys, rbac permission list, AUTH_REQUIRED backward-compat contract) and the persistence layer (memory vs postgres backend switch, migration workflow, what byte-identical-behavior guarantee the default actually preserves)
- *AI output summary:* Two docs covering the auth and persistence subsystems for the rest of the team and future contributors.
- *Decision:* Accepted as-is
- *If modified/rejected, why:* n/a
- *How it was validated:* Cross-checked against `auth_router.py` and the repository implementations for accuracy.
- *Bugs found (if any) and resolution:* None.

---

### Entry #38 — bulk_evaluate.py + seed_active_policy.py + override_decision.py
- *Timestamp / author:* 2026-07-25 03:20 UTC — Shubham Kumar <kshubhamsharma464@gmail.com>
- *AI tool + model:* Claude Code (Anthropic) — model: claude-sonnet-4-5
- *Task / module:* `app/application/use_cases/bulk_evaluate.py`, `seed_active_policy.py`, `override_decision.py`
- *Prompt (verbatim):*
  > bulk_evaluate - up to BULK_EVALUATE_MAX_ITEMS incidents per request, per-item isolation so one bad item doesnt fail the whole batch. seed_active_policy - on startup, if theres no active pack for DYNAMIC_RULE_SET_NAME yet, seed/publish/activate it from the fixture, once, never overwrite real data. override_decision - let an authorized human manually override a Decisions outcome but keep the original around for audit
- *AI output summary:* Three use cases; `bulk_evaluate` wraps each item in try/except, `seed_active_policy` checks for an existing active pack first, `override_decision` writes a `ManualOverride` entity alongside the original `Decision`.
- *Decision:* Modified
- *If modified/rejected, why:* `bulk_evaluate` first draft aborted the whole batch on the first invalid incident payload. Changed to isolate failures per item.
- *How it was validated:* Tests with a batch containing one malformed incident, asserting the rest still evaluate; `test_manual_override.py` for the override path.
- *Bugs found (if any) and resolution:* As above (whole-batch abort) — fixed.

---

### Entry #39 — rule_pack_router.py + rule_router.py
- *Timestamp / author:* 2026-07-25 03:40 UTC — Shubham Kumar <kshubhamsharma464@gmail.com>
- *AI tool + model:* Claude Code (Anthropic) — model: claude-sonnet-4-5
- *Task / module:* `app/interfaces/api/rule_pack_router.py`, `rule_router.py`
- *Prompt (verbatim):*
  > wire the rule pack lifecycle (publish/activate/rollback/promote-to-shadow) n individual rule crud as rest endpoints under /api/v1/rule-packs n /api/v1/rules, gated by the rules:edit/publish/activate perms
- *AI output summary:* Two routers exposing the lifecycle and CRUD use cases with permission-gated dependencies.
- *Decision:* Accepted as-is
- *If modified/rejected, why:* n/a
- *How it was validated:* `tests/test_rule_management_api.py` covering the full CRUD + lifecycle surface and RBAC per endpoint.
- *Bugs found (if any) and resolution:* None.

---

### Entry #40 — simulation_router.py + app/jobs/
- *Timestamp / author:* 2026-07-25 04:00 UTC — Shubham Kumar <kshubhamsharma464@gmail.com>
- *AI tool + model:* Claude Code (Anthropic) — model: claude-sonnet-4-5
- *Task / module:* `app/interfaces/api/simulation_router.py`, `app/jobs/escalation_sweep.py`, `sla_breach_sweep.py`, `shadow_mode_diff_runner.py`
- *Prompt (verbatim):*
  > simulation_router should expose simulate/replay/compare endpoints. escalation_sweep - periodic job escalating unacknowledged incidents past their sla breach threshold, needs to be idempotent, running it twice shouldnt double escalate. shadow_mode_diff_runner - periodically diff shadow-pack output against active-pack output for the same recent incidents
- *AI output summary:* Router plus three job modules, `escalation_sweep` checking `Incident.escalated_at` before acting.
- *Decision:* Modified
- *If modified/rejected, why:* `escalation_sweep` first draft re-escalated an incident on every sweep run until acknowledged, generating duplicate escalation entries. Added an `escalated_at` guard.
- *How it was validated:* `tests/test_jobs.py` running the sweep twice back-to-back on the same fixture incident, asserting exactly one escalation entry.
- *Bugs found (if any) and resolution:* As above (duplicate escalations) — fixed.

---

### Entry #41 — Rule platform test bundle
- *Timestamp / author:* 2026-07-25 04:20 UTC — Shubham Kumar <kshubhamsharma464@gmail.com>
- *AI tool + model:* Claude Code (Anthropic) — model: claude-sonnet-4-5
- *Task / module:* `tests/test_rule_cache.py`, `test_rule_management_api.py`, `test_rule_pack_lifecycle.py`, `test_simulation_api.py`, `test_dynamic_rule_source.py`, `test_manual_override.py`, `test_jobs.py`
- *Prompt (verbatim):*
  > need to fill out remaining coverage for the rule platform - rulecache L1/L2/L3 fallback w fakeredis, dynamic rule source end to end (create -> publish -> activate -> serves live evaluations), n anything from earlier entries not covered by its own test file yet
- *AI output summary:* Broadened/completed the seven test files across the rule management, cache, and simulation surface.
- *Decision:* Accepted as-is
- *If modified/rejected, why:* n/a
- *How it was validated:* Full local run of the seven files plus the earlier rule-pack loader tests from Entry #22, all green.
- *Bugs found (if any) and resolution:* None beyond what was already fixed in Entries #17 (rejected, no code), #26, #29, #35, #40.

---

### Entry #42 — docs: rule-management.md + simulation.md
- *Timestamp / author:* 2026-07-25 04:40 UTC — Shubham Kumar <kshubhamsharma464@gmail.com>
- *AI tool + model:* Claude Code (Anthropic) — model: claude-sonnet-4-5
- *Task / module:* `docs/rule-management.md`, `docs/simulation.md`
- *Prompt (verbatim):*
  > document the rule pack lifecycle end to end (draft/published/active/shadow, rollback), the dynamic rule source switch, the redis L2 cache design n its fallback behavior, n the simulation/replay/compare/bulk-evaluate surface w their safety caps
- *AI output summary:* Two docs covering the entire rule management + simulation platform for the team.
- *Decision:* Accepted as-is
- *If modified/rejected, why:* n/a
- *How it was validated:* Cross-checked against the routers and use cases for accuracy before committing.
- *Bugs found (if any) and resolution:* None.

---

### Entry #43 — AI provider interface + StubAIProvider + factory
- *Timestamp / author:* 2026-07-25 09:00 UTC — Yaman Chowdhary <ychowdhary1@gmail.com>
- *AI tool + model:* Claude Code (Anthropic) — model: claude-opus-4-5
- *Task / module:* `app/domain/interfaces/ai_provider.py`, `app/infrastructure/ai/stub_ai_provider.py`, `factory.py`
- *Prompt (verbatim):*
  > need an AIProvider interface (generate_rule, document_rule, explain_decision) and a deterministic StubAIProvider as the default, since we got no live llm endpoint reachable in this sandbox. it should never make up a conditions tree outta vague input, flag it for review instead, same as a real llm-backed provider oughta do
- *AI output summary:* `AIProvider` ABC; `StubAIProvider` using keyword/threshold/action-keyword extraction with a conservative fallback; `create_ai_provider(settings)` factory.
- *Decision:* Accepted as-is
- *If modified/rejected, why:* n/a
- *How it was validated:* `tests/test_ai_providers.py` — extraction cases plus the conservative-fallback path for vague input.
- *Bugs found (if any) and resolution:* None.

---

### Entry #44 — prompts.py + OpenAI/Gemini-compatible providers
- *Timestamp / author:* 2026-07-25 09:30 UTC — Yaman Chowdhary <ychowdhary1@gmail.com>
- *AI tool + model:* Claude Code (Anthropic) — model: claude-opus-4-5
- *Task / module:* `app/infrastructure/ai/prompts.py`, `openai_compatible_provider.py`, `gemini_compatible_provider.py`, `common.py`
- *Prompt (verbatim):*
  > write the system prompts (rule generation, rule documentation, decision explanation) that spell out the exact json shape n operator list expected back, instead of just a vague "match the schema" reference. also implement openai-compatible n gemini-compatible providers against those prompts, both need to be testable w/o a live network call
- *AI output summary:* Three system prompts; two HTTP-backed providers each constructing an `httpx.Client` with an injectable `transport`.
- *Decision:* Modified
- *If modified/rejected, why:* First draft of the providers called the module-level `httpx.post(...)` directly — untestable without a real network call, since `httpx.MockTransport` only plugs into `httpx.Client(transport=...)`. Refactored to build the client internally. Also, markdown-fenced JSON (```json ... ```) broke `json.loads()` on some model outputs — fixed in `common.py`'s `extract_json_object()` with fence-stripping and a regex fallback.
- *How it was validated:* `tests/test_ai_providers.py` against `httpx.MockTransport` — real HTTP-call/parsing/error-handling paths exercised, not the providers' own methods mocked.
- *Bugs found (if any) and resolution:* As above (transport injection, markdown fences) — both fixed.

---

### Entry #45 — Rejected: auto-publish shortcut for AI-generated rules
- *Timestamp / author:* 2026-07-25 10:00 UTC — Yaman Chowdhary <ychowdhary1@gmail.com>
- *AI tool + model:* Claude Code (Anthropic) — model: claude-opus-4-5
- *Task / module:* `app/application/use_cases/generate_rule_from_description.py`
- *Prompt (verbatim):*
  > for a smoother ux, could generate_rule just save the draft directly as a new rule via RulePackRepository too? so the reviewer just edits n activates instead of having to resubmit it to POST /api/v1/rules manually, seems like an extra step for no reason
- *AI output summary:* A variant of the use case that persisted the AI-drafted rule directly to the repository before returning it.
- *Decision:* Rejected
- *If modified/rejected, why:* Violates the project's structural AI safety boundary — no AI-influenced code path is allowed to make a rule exist in the system without an explicit human `POST /api/v1/rules` call. The UX convenience wasn't worth breaking that guarantee.
- *How it was validated:* n/a — reverted before merging.
- *Bugs found (if any) and resolution:* n/a. Codified as a permanent regression test instead: `test_generate_rule_returns_draft_without_persisting_anything`.

---

### Entry #46 — External stub context providers
- *Timestamp / author:* 2026-07-25 10:20 UTC — Yaman Chowdhary <ychowdhary1@gmail.com>
- *AI tool + model:* Claude Code (Anthropic) — model: claude-sonnet-4-5
- *Task / module:* `app/infrastructure/external/base_stub_provider.py`, `crm_provider.py`, `workforce_provider.py`, `vendor_kb_provider.py`, `competitive_intel_provider.py`, `social_listening_provider.py`, `historical_context_provider.py`, `regional_policy_provider.py`, `incident_correlation_provider.py`
- *Prompt (verbatim):*
  > need stub impls of ContextProvider for every external data source the spec mentions (crm, workforce, vendor kb, competitive intel, social listening, historical context, regional policy, incident correlation) - deterministic canned responses keyed off incident fields since none of these have real integrations yet obviously
- *AI output summary:* Nine stub providers sharing a `BaseStubProvider` with deterministic, incident-keyed canned data.
- *Decision:* Accepted as-is
- *If modified/rejected, why:* n/a
- *How it was validated:* Fed into `context_aggregation_service.py` (Entry #10) fixture tests, confirming merge behavior with real provider instances rather than mocks.
- *Bugs found (if any) and resolution:* None.

---

### Entry #47 — generate_rule_from_description.py + document_rule.py
- *Timestamp / author:* 2026-07-25 10:45 UTC — Yaman Chowdhary <ychowdhary1@gmail.com>
- *AI tool + model:* Claude Code (Anthropic) — model: claude-sonnet-4-5
- *Task / module:* `app/application/use_cases/generate_rule_from_description.py`, `document_rule.py`
- *Prompt (verbatim):*
  > generate_rule_from_description - natural language -> draft rule via AIProvider, run it thru ValidateRuleUseCase, return the draft + validation result w/o persisting anything (per the idea we rejected earlier). document_rule - ai generated prose docs for an existing or draft rule, read only, no writes
- *AI output summary:* Two use cases, both provider-agnostic (depend only on the `AIProvider` interface from Entry #43).
- *Decision:* Accepted as-is
- *If modified/rejected, why:* n/a
- *How it was validated:* `tests/test_ai_api.py::test_generate_rule_returns_draft_without_persisting_anything` (repo diff assertion), document-rule by id and by inline payload.
- *Bugs found (if any) and resolution:* None.

---

### Entry #48 — explain_decision_ai.py
- *Timestamp / author:* 2026-07-25 11:05 UTC — Yaman Chowdhary <ychowdhary1@gmail.com>
- *AI tool + model:* Claude Code (Anthropic) — model: claude-opus-4-5
- *Task / module:* `app/application/use_cases/explain_decision_ai.py`
- *Prompt (verbatim):*
  > explain_decision has to run strictly after EvaluateIncidentUseCase already produced n persisted a Decision. it should read a plain fact snapshot n return ai-narrated prose for a non technical reader, additive to the deterministic explanation, never a substitute for it, n never fed back into the decision itself
- *AI output summary:* Use case building a local `_decision_facts()` dict from an existing `Decision`, passed to `AIProvider.explain_decision()`.
- *Decision:* Modified
- *If modified/rejected, why:* First draft imported `app.interfaces.api.serializers.decision_to_dict` — an application-layer use case reaching into the interfaces layer, inverting Clean Architecture's dependency rule even though it happened to work at runtime. Fixed with a local helper instead.
- *How it was validated:* `tests/test_ai_api.py::test_explain_decision_returns_both_explanations`; code review confirming no write path exists from the use case to any repository.
- *Bugs found (if any) and resolution:* As above (interfaces-layer import from application layer) — fixed.

---

### Entry #49 — ai_router.py + schemas.py + serializers.py
- *Timestamp / author:* 2026-07-25 11:30 UTC — Yaman Chowdhary <ychowdhary1@gmail.com>
- *AI tool + model:* Claude Code (Anthropic) — model: claude-sonnet-4-5
- *Task / module:* `app/interfaces/api/ai_router.py`, `schemas.py`, `serializers.py`
- *Prompt (verbatim):*
  > wire generate-rule/document-rule/explain-decision as post endpoints under /api/v1/ai, plus the pydantic request/response schemas n entity-to-dict serializers the whole api layer can share. AIProviderError should turn into a 502, not a 500 or some silently degraded fake success
- *AI output summary:* `ai_router.py`, shared `schemas.py`/`serializers.py`, `AIProviderError` → `502` mapping.
- *Decision:* Accepted as-is
- *If modified/rejected, why:* n/a
- *How it was validated:* Fault-injected provider raising `AIProviderError` asserted to surface as `502`.
- *Bugs found (if any) and resolution:* None.

---

### Entry #50 — incident_router.py + decision_router.py + health_router.py
- *Timestamp / author:* 2026-07-25 11:55 UTC — Yaman Chowdhary <ychowdhary1@gmail.com>
- *AI tool + model:* Claude Code (Anthropic) — model: claude-sonnet-4-5
- *Task / module:* `app/interfaces/api/incident_router.py`, `decision_router.py`, `health_router.py`
- *Prompt (verbatim):*
  > incident_router - post /incidents/evaluate (single) + bulk-evaluate. decision_router - read decisions, apply manual overrides. health_router - /health for the docker healthcheck n load balancers, should report db/cache reachability when the backend is postgres/redis
- *AI output summary:* Three routers wiring the remaining use cases from Entries #23/#27/#35/#38.
- *Decision:* Accepted as-is
- *If modified/rejected, why:* n/a
- *How it was validated:* `tests/test_api_incident.py`, `test_decision_router.py`.
- *Bugs found (if any) and resolution:* None.

---

### Entry #51 — dependencies.py + lifespan.py + main.py
- *Timestamp / author:* 2026-07-25 12:20 UTC — Yaman Chowdhary <ychowdhary1@gmail.com>
- *AI tool + model:* Claude Code (Anthropic) — model: claude-opus-4-5
- *Task / module:* `app/interfaces/api/dependencies.py`, `lifespan.py`, `app/main.py`
- *Prompt (verbatim):*
  > this is basically the composition root now - dependencies.py needs to construct every repo/service/provider exactly once based off Settings n expose them as fastapi deps; lifespan.py runs startup seeding/cache warmup; main.py assembles the fastapi app n registers every router + middleware from everyones work tonite. big one, take your time
- *AI output summary:* `dependencies.py` branching on `persistence_backend`/`cache_backend`/`ai_provider` to construct the right concrete implementations; `lifespan.py` calling `seed_active_policy` and warming the rule cache; `main.py` registering all eight routers plus both middleware.
- *Decision:* Accepted as-is
- *If modified/rejected, why:* n/a
- *How it was validated:* Full app boots against every backend combination (`memory`/`postgres` × `memory`/`redis` × `stub`/`openai_compatible`); the entire test suite run against the assembled app.
- *Bugs found (if any) and resolution:* None.

---

### Entry #52 — scripts/
- *Timestamp / author:* 2026-07-25 12:45 UTC — Yaman Chowdhary <ychowdhary1@gmail.com>
- *AI tool + model:* Claude Code (Anthropic) — model: claude-sonnet-4-5
- *Task / module:* `scripts/`
- *Prompt (verbatim):*
  > need operator scripts - seed_base_rule_pack.py for explicit (non auto) seeding, n a couple one off maintenance scripts for creating an initial admin user n rotating a jwt secret on a running deployment
- *AI output summary:* CLI scripts under `scripts/`, each a thin wrapper calling the relevant use case with a real `Settings`-driven dependency set.
- *Decision:* Accepted as-is
- *If modified/rejected, why:* n/a
- *How it was validated:* Ran each script against a scratch Postgres + Redis stack.
- *Bugs found (if any) and resolution:* None.

---

### Entry #53 — Dockerfile + Dockerfile.dev + docker-compose*.yml + run scripts
- *Timestamp / author:* 2026-07-25 13:10 UTC — Yaman Chowdhary <ychowdhary1@gmail.com>
- *AI tool + model:* Claude Code (Anthropic) — model: claude-sonnet-5
- *Task / module:* `Dockerfile`, `Dockerfile.dev`, `docker-compose.yml`, `docker-compose.dev.yml`, `docker-run.sh`, `run.sh`, `run.ps1`
- *Prompt (verbatim):*
  > need a multi stage production dockerfile - python:3.11-slim builder pip installing into a throwaway prefix, slim runtime stage copying only the installed packages + app code, non root user, healthcheck against /health. also a Dockerfile.dev w live reload. docker-compose.yml wiring api + postgres + redis, w alembic upgrade head n the seed scripts runnable via `docker compose run --rm api ...`
- *AI output summary:* Two-stage Dockerfile as committed — non-root `app` user, `HEALTHCHECK` via `urllib` against `localhost:8000/health`; compose files for prod and dev; run scripts for both POSIX and PowerShell.
- *Decision:* Modified
- *If modified/rejected, why:* First draft of the runtime stage excluded `migrations/`, `alembic.ini`, and `scripts/` to keep the image minimal, which broke `docker compose run --rm api alembic upgrade head` and the seed scripts with "alembic.ini not found". Added them back explicitly.
- *How it was validated:* `docker build -t pulseguard-dap:latest .` completed successfully (305MB image, 71.3MB compressed layers), confirmed via `docker images`; `docker compose run --rm api alembic upgrade head` verified against the compose stack.
- *Bugs found (if any) and resolution:* As above (missing `alembic.ini`/`migrations/`/`scripts/` in the runtime stage) — fixed.

---

### Entry #54 — AI/API test bundle
- *Timestamp / author:* 2026-07-25 13:35 UTC — Yaman Chowdhary <ychowdhary1@gmail.com>
- *AI tool + model:* Claude Code (Anthropic) — model: claude-sonnet-5
- *Task / module:* `tests/test_ai_api.py`, `test_ai_providers.py`, `test_openapi_schema.py`, `test_api_incident.py`, `test_decision_router.py`
- *Prompt (verbatim):*
  > need to round out coverage for the ai n api layer - rbac per ai endpoint (editor can generate/document but not explain-decision, viewer cant generate-rule at all), openapi schema validity for every router, incident/decision router edge cases (404s, malformed payloads)
- *AI output summary:* Five test files completing the AI/API layer's coverage.
- *Decision:* Accepted as-is
- *If modified/rejected, why:* n/a
- *How it was validated:* Full regression run: all tests green with `AI_PROVIDER=stub`.
- *Bugs found (if any) and resolution:* None beyond what was already fixed in Entries #44, #48, #53.

---

### Entry #55 — docs: ai-assist.md, architecture-review.md, AI_ENGINEERING_LOG.md, industry-sop-gap-closure.md, customer-sla-rule-pack.md
- *Timestamp / author:* 2026-07-25 13:55 UTC — Yaman Chowdhary <ychowdhary1@gmail.com>
- *AI tool + model:* Claude Code (Anthropic) — model: claude-sonnet-5
- *Task / module:* `docs/ai-assist.md`, `docs/architecture-review.md`, `docs/AI_ENGINEERING_LOG.md`, `docs/industry-sop-gap-closure.md`, `docs/customer-sla-rule-pack.md`
- *Prompt (verbatim):*
  > document the ai-assist features safety boundary n provider abstraction, do a whole system architecture review now that every layer is finally wired together, write the engineering log for the ai work specifically (prompts we tried, bugs found), n closeout notes for the industry-sop n customer-sla rule pack fixtures
- *AI output summary:* Five docs closing out the sprint's documentation, cross-referencing the routers/use cases/services built by all four contributors.
- *Decision:* Accepted as-is
- *If modified/rejected, why:* n/a
- *How it was validated:* Reviewed against the final assembled `app/main.py` and full test suite for accuracy.
- *Bugs found (if any) and resolution:* None.

---

### Entry #56 — AI usage logger
- *Timestamp / author:* 2026-07-25 14:15 UTC — Tamanna Agnihotri <tamannaa.agnihotri@gmail.com>
- *AI tool + model:* Claude Code (Anthropic) — model: claude-sonnet-5
- *Task / module:* `app/infrastructure/ai/usage_logger.py`, `app/infrastructure/ai/factory.py`, `app/core/settings.py`, `docs/ai-usage-log.md`
- *Prompt (verbatim):*
  > can u add a usage_logger module that appends a new "### Entry #N" block to docs/ai-usage-log.md in our standard template, every time an AIProvider method actually runs. also need a manual log_ai_entry() helper for logging ai assisted coding sessions that dont go thru the AIProvider interface. wire it into factory.create_ai_provider() behind an off-by-default AI_USAGE_LOG_ENABLED setting so it doesnt mess w existing tests unless we turn it on explicitly
- *AI output summary:* `usage_logger.py` (`AIUsageLogger` class, `log_ai_call` decorator, `wrap_provider_with_logging`, `log_ai_entry` manual helper); `Settings.ai_usage_log_enabled = False`; `factory.py` wraps the constructed provider when the flag is enabled.
- *Decision:* Accepted as-is
- *If modified/rejected, why:* n/a
- *How it was validated:* Full test suite (196 tests) re-run to confirm the factory change is a no-op by default; manual test with the flag enabled confirmed a well-formed entry is appended with the correct auto-incremented number, and confirmed no file writes occur with the flag left at its default `False`.
- *Bugs found (if any) and resolution:* None.
