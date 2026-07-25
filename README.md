# Pulse Guard Decision Automation Platform -- working vertical slice

This is the first buildable slice of the Telecom Network Incident Decision
Automation Platform, built per `architecture-review.md`'s recommended
sequencing: the critical path (policy engine, conflict resolution, risk
scoring, execution planning, compliance constraints, explainability) proven
end-to-end against the seeded 35-rule pack, before wiring real Postgres,
background jobs, or auth.

## What's real and tested right now

- **`app/engine/`** -- a domain-agnostic JsonLogic-style evaluator (`var`,
  `and`, `or`, `==`, `>`, `<`, `>=`, `<=`, `in`) implemented as a Strategy
  pattern / plugin registry. Never imports from `app.domain` -- that boundary
  is what makes the rule pack swappable across verticals.
- **`app/domain/`** -- entities (`Rule`, `RulePack`, `Incident`, `Decision`),
  the `RuleCondition` value object bridging domain and engine, and the
  services that implement the design doc's core algorithms: `policy_engine.py`
  (family-ordered evaluation with exception self-veto), `conflict_resolver.py`
  (suppressor pass -> conflict-group pass -> field merge, design doc §3b),
  `risk_scorer.py` (additive secondary signal, §3c), `compliance_applier.py`
  (post-resolution constraint pass, §6.5), `execution_plan_builder.py`
  (ordered plan with retry/fallback sequencing, §3d), `explainability_builder.py`.
- **`app/application/orchestrator.py`** -- runs the full pipeline; shared by
  `evaluate_incident` (real path) and `simulate_rules` (dry-run/shadow-mode path).
- **`app/infrastructure/repositories/in_memory_rule_repository.py`** -- loads
  all 35 seeded rules from `app/infrastructure/data/rules-seed.json` at
  startup. This is the fixture-backed stand-in `docs/architecture-review.md` §5
  recommends building against before a real Postgres-backed repository; swap
  it for one behind the same `RuleRepository` interface later, no domain/
  or application/ code changes. Left completely untouched by every rule-pack
  addition below -- `tests/conftest.py` still constructs it bare.
- **Six externally-authored or audit-derived rule packs, merged additively**
  via `CompositeRuleRepository`, wired only in the API's composition root
  (`app/interfaces/api/dependencies.py`): a telecom SLA pack (8 source rules
  -> 12 native), a generic customer-request-workflow pack (30 rules), a
  customer/SLA priority-decision pack (18 rules), a historical/
  operational-pattern pack (30 rules), a network/infrastructure pack
  (20 source rules -> 14 native; 6 skipped as duplicates of the customer/SLA
  pack), and a 3-rule industry-SOP gap-closure pack (vendor UPC escalation,
  change-freeze governance, mass-outage regulatory reporting threshold --
  added after auditing the rule base against real telecom NOC/ITIL SOPs and
  confirming most categories, like security triage and auto-remediation,
  were already covered) -- 142 rules total evaluated together in one pass.
  Full integration record for the five externally-authored packs:
  `docs/customer-sla-rule-pack.md`. The SOP audit and what it found already
  covered vs. genuinely missing: `docs/industry-sop-gap-closure.md`.
- **`EscalationPolicy` seeding** (`app/infrastructure/repositories/in_memory_escalation_policy_repository.py`)
  -- the acknowledgment-SLA auto-escalation mechanism (`EscalationSweep` job,
  `EscalationPolicy`/`EscalationEvent` entities) existed from the original
  fix-list work but had no real policy data to walk. Now seeded with one
  policy per severity band using `schema.sql`'s own level vocabulary
  (ENGINEER -> REGIONAL_MANAGER -> NATIONAL_NOC -> VENDOR -> OEM).
- **`app/interfaces/api/`** -- FastAPI `POST /api/v1/incidents/evaluate`,
  `GET /health`, `GET|POST /api/v1/decisions/...`, (Phase 2)
  `POST /api/v1/auth/{register,login,refresh}`, `GET /api/v1/auth/me`,
  (Phase 2.5) full
  `/api/v1/rule-packs` and `/api/v1/rules` CRUD/versioning/publish/
  activate/rollback plus `/api/v1/incidents` create/get/list/bulk (see
  `docs/rule-management.md`), (Phase 3) `/api/v1/ai/generate-rule`,
  `/api/v1/ai/document-rule`, `/api/v1/ai/explain-decision/{incident_id}`
  (see `docs/ai-assist.md`), and (Phase 4) `/api/v1/simulate`,
  `/api/v1/simulate/replay`, `/api/v1/simulate/compare`,
  `/api/v1/evaluate/bulk`, `/api/v1/decisions/distribution` (see
  `docs/simulation.md`).
- **`tests/`** -- 196 passing tests (94 from the original build + Phase 1
  persistence, 31 from Phase 2 auth/RBAC, 22 from Phase 2.5 dynamic rule
  management, 27 from Phase 3 AI-assisted authoring, and 21 from Phase 4
  simulation + bulk evaluation -- 20 HTTP/use-case tests covering what-if,
  replay, compare, bulk evaluate persist/dry-run/failure-isolation/cap
  enforcement, decision distribution, and RBAC, plus 1 Postgres round-trip
  test for `DecisionRepository.list_all`): the original 10 plus 25 from
  the architecture-review fix list, plus 50 covering the four new
  JsonLogic operators, all six rule-pack loaders (including the network/
  infrastructure pack's dedup logic and its cross-pack policy disagreement
  with the customer/SLA pack, and the SOP pack's reuse of previously-unset
  base-pack fields), the seeded escalation policies running end to end
  through `EscalationSweep`, and explicit backward-compatibility locks
  (bare `InMemoryRuleRepository()` still exactly 35 rules; INC-101 still
  matches the identical rule set through the fully 7-pack-merged
  repository).

## Project documentation

- **`docs/decision-engine-design.md`** -- the full rule-base design: pipeline,
  conflict resolution algorithm, risk scoring, execution plan generation,
  compliance constraint pass, mitigation policies, all 35 rules, and edge cases.
- **`docs/tradeoffs.md`** -- architecture decision record, one entry per major
  choice (database, conflict resolution, versioning, caching, auth, etc.),
  corrected against what's actually implemented (see `architecture-review.md`
  §3 for what was wrong in the first draft and why).
- **`docs/architecture-review.md`** -- the gap analysis this build's sequencing
  was based on: what the folder structure and Tradeoffs.md got right, what had
  no home in the tree, and the prioritized fix list.
- **`app/infrastructure/database/schema.sql`** -- the full PostgreSQL/JSONB
  schema (11 tables) that the in-memory repository stands in for today. This
  is the canonical schema location -- there is deliberately no separate
  top-level `alembic/`, per architecture-review.md\'s note that having both
  reads as an unresolved duplication rather than a decision.
- **`app/infrastructure/data/rules-seed.json`** -- the canonical 35-rule seed
  data, identical to the one referenced throughout `docs/`. Both the running
  code and the documentation read from this single file, so they can\'t drift
  from each other the way the hand-traced INC-101 example once did.
- **`docs/customer-sla-rule-pack.md`** -- how the three externally-authored
  rule packs (SLA telecom, generic customer-workflow, CSR-SLA
  priority-decision) were transpiled into native rules, why each one can\'t
  have broken anything that existed before it, every deliberate
  field-namespace overlap left unreconciled, and the verification performed.
- **`docs/industry-sop-gap-closure.md`** -- the audit against real telecom
  NOC/ITIL SOPs: what was already covered (security triage, auto-
  remediation, major-incident comms, regulatory reporting) vs. the three
  genuine gaps closed (vendor UPC escalation, change-freeze governance,
  mass-outage regulatory threshold), plus the escalation-policy seeding
  that made the previously-unfed `EscalationSweep` job usable end to end.
- **`docs/persistence.md`** -- the PostgreSQL/SQLAlchemy/Alembic
  persistence layer: what's Postgres-backed vs. still in-memory, the
  entity-mapping rationale, the deliberate scope boundary (the hot
  evaluation path still reads the in-memory rule packs), and how to run
  migrations and seed scripts.
- **`docs/auth.md`** -- JWT + API-key auth, RBAC, rate limiting, security
  headers: the permission model, the exact backward-compatibility
  mechanism (`AUTH_REQUIRED=false` by default), how to exercise it
  locally, and what's explicitly not included yet (role assignment via
  API, token revocation, OAuth/SSO).
- **`docs/rule-management.md`** -- the dynamic Rule Management platform:
  full rule/rule-pack CRUD, versioning (Draft/Published/Active/Deprecated/
  Archived), publish/activate/rollback, a cache-fronted hot path that goes
  live with zero restart (`RULE_SOURCE=dynamic`), Editor vs Policy Admin
  RBAC, audit trail, and the `/api/v1/incidents` REST resource.
- **`docs/ai-assist.md`** -- AI-assisted rule authoring: the structural
  (not just policy) safety boundary that keeps AI non-authoritative, the
  Strategy/Factory provider abstraction (stub/OpenAI-compatible/
  Gemini-compatible, configured via `.env` only), prompts, failure
  handling, the three `/api/v1/ai/*` endpoints, and what's not included
  yet. `docs/AI_ENGINEERING_LOG.md` -- prompt-design rationale, bugs found
  and fixed while building the two LLM-backed providers, and lessons for
  adding a fourth provider.
- **`docs/simulation.md`** -- what-if analysis, historical replay, rule-
  version comparison, and bulk evaluation with aggregate metrics (Phase
  4): why every use case shares the real production orchestrator instead
  of a second approximation of it, rule-pack reference resolution
  (active vs. an explicit versioned/Draft pack), the four new endpoints,
  the safety caps, and RBAC.

## Prioritized fix list from architecture-review.md §6 -- status

1. ~~Fix Tradeoffs.md #4/#12/#13~~ -- done (`docs/tradeoffs.md`).
2. ~~Context Aggregation Layer explicit module~~ -- done. `app/domain/interfaces/context_provider.py`
   (port) + `app/domain/services/context_aggregation_service.py` (fan-out, per-source
   failure isolation) + 8 STUB adapters under `app/infrastructure/external/`, one per
   source system named in the design doc §2 table. Wired into `EvaluateIncidentUseCase`;
   a provider failing degrades only that source and lowers `confidenceScore` --
   it never blocks the decision. Real adapters (HTTP/DB calls) replace the STUB
   `fetch()` bodies behind the same `ContextProvider` interface.
3. ~~Missing use cases + entities/repositories~~ -- done. `validate_rule_pack`,
   `promote_to_shadow`, `rollback_rule_pack`, `override_decision`,
   `acknowledge_escalation`, plus `ManualOverride`/`EscalationEvent`/`EscalationPolicy`
   entities and their in-memory repositories.
4. ~~`jobs/` scheduler layer~~ -- done as plain callable job classes
   (`app/jobs/sla_breach_sweep.py`, `escalation_sweep.py`, `shadow_mode_diff_runner.py`).
   Not yet wired to an actual scheduler (APScheduler/Celery beat/cron) -- that's
   the next step once there's a real deployment target to schedule against.
5. ~~Resolve `alembic/` duplication, clarify incident_router vs decision_router~~ --
   done. Canonical schema lives at `app/infrastructure/database/schema.sql`, no
   stray top-level `alembic/`. `incident_router.py` = submission (POST, creates a
   decision), `decision_router.py` = retrieval (GET, read-only, never evaluates).
6. ~~Four missing tradeoff entries + cache-invalidation decision~~ -- done
   (`docs/tradeoffs.md` #24-27, and #17 now states push-based invalidation via
   `app/core/cache.py` as primary with a 10s TTL fallback, wired into
   `InMemoryRulePackRepository.activate()`).

Swagger/OpenAPI: `IncidentEvaluateRequest`/`DecisionResponse` and friends are
real Pydantic models (`app/interfaces/api/schemas.py`) with field descriptions
and a worked INC-101 example, `response_model` set on every route, and the
FastAPI app carries full title/description/tags metadata -- `/docs` renders a
complete, browsable Swagger UI, not a raw-dict placeholder.

## What's still stubbed / not built yet

- **PostgreSQL is wired up for decision/rule-pack/audit/escalation history**
  (`PERSISTENCE_BACKEND=postgres`, see `docs/persistence.md`) but the hot
  incident-evaluation path still reads the in-memory composite of all 7
  rule packs -- moving that into Postgres is real future work, not done
  here (deliberately scoped out; see `dependencies.py`'s module docstring).
- Context Aggregation Layer providers are STUBs returning static defaults, not
  real HTTP/DB integrations.
- `jobs/` classes aren't wired to an actual scheduler yet.
- **Auth/RBAC is done** (Phase 2 -- JWT + role-based permissions,
  rate limiting, security headers; see `docs/auth.md`), but off by default
  (`AUTH_REQUIRED=false`). Not yet included: role assignment via API
  (roles are only set at registration), token
  revocation/blocklists, and OAuth/SSO. No DI container beyond the
  `dependencies.py` composition root.
- **Dynamic Rule Management is done** (Phase 2.5 -- rule/rule-pack CRUD,
  versioning, publish/activate/rollback, live-without-restart evaluation
  via `RULE_SOURCE=dynamic`, Editor/Policy Admin RBAC, audit trail,
  `/api/v1/incidents` REST resource; see `docs/rule-management.md`), but
  the hot evaluation path stays on the original 142-rule fixture composite
  by default (`RULE_SOURCE=static`). Not yet included: automatic
  empty-database seeding on startup (a script/API call away, not
  automatic), hash-chain audit tamper detection, and an independent
  rule-lookup index (rule-by-id is currently a linear scan).
- **AI-assisted rule authoring is done** (Phase 3 -- NL-to-rule-JSON
  generation, AI rule documentation, AI decision-explanation narration,
  configurable via `.env` between a deterministic offline stub and
  OpenAI-/Gemini-compatible endpoints; see `docs/ai-assist.md`), and AI
  is structurally prevented from ever creating/publishing/activating a
  rule or a decision -- proven by a test asserting the rule-pack
  repository is byte-identical before/after a generate-rule call. Not yet
  included: AI-assisted test generation, live OpenAI/Gemini credentials
  weren't available to test against (verified via `httpx.MockTransport`
  instead), no streaming responses.
- **Simulation + bulk evaluation is done** (Phase 4 -- what-if analysis,
  historical replay/impact analysis, rule-version comparison, and bulk
  evaluation with success/failure counts, decision distribution, and
  execution metrics; see `docs/simulation.md`). Every use case shares the
  real production `PipelineOrchestrator` instance (and, for bulk evaluate,
  the real `EvaluateIncidentUseCase`) rather than a parallel
  implementation. `PromoteToShadowUseCase` (Phase 1's gated shadow-
  promotion workflow) is unchanged and untouched by this -- comparison is
  a separate, ungated, read-only tool. No new database tables/migration
  were needed.
- `incident_category_map` classification lookup isn't wired in; `incidentCategory`
  isn't populated on the decision yet.

## Running it

### Option A -- local venv

```bash
./run.sh                # creates .venv, installs deps, starts the server with reload (tests skipped for now)
./run.sh --with-tests    # same, but also runs the test suite first
./run.sh --test-only     # install + test only, no server
```

Windows without WSL/Git Bash: use `run.ps1` instead (`.\run.ps1`, `.\run.ps1 -TestOnly`).

Or by hand:

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload          # http://127.0.0.1:8000/docs for interactive API docs
pytest -v                              # run the test suite
```

### Option B -- Docker

```bash
./docker-run.sh              # build + run the production image (Dockerfile), foreground
./docker-run.sh --dev        # build + run the dev image (Dockerfile.dev) with hot reload, source bind-mounted
./docker-run.sh --detach     # run in the background
./docker-run.sh --logs       # tail logs of the running stack
./docker-run.sh --down       # stop and remove the stack
```

Requires Docker Desktop (or Docker Engine + the Compose v2 plugin). Under
the hood: `Dockerfile` is a multi-stage production build (slim runtime,
non-root user, healthcheck against `/health`); `Dockerfile.dev` installs
straight into a single stage and runs `uvicorn --reload` against a
bind-mounted `app/`/`tests/` tree so host edits take effect without a
rebuild. `docker-compose.yml` / `docker-compose.dev.yml` each include a
`db` (Postgres 16) service with a healthcheck the `api` service waits on.

`./docker-run.sh` is fully zero-touch: it builds, starts Postgres, waits
for it to report healthy, runs `alembic upgrade head`, then seeds default
roles/permissions/escalation policies/base rule pack -- all before
starting the API. Every seed step is idempotent (skips anything already
present), so re-running `./docker-run.sh` any number of times, including
against a database that already has data, is always safe. Nothing manual
to run yourself.

Set `PERSISTENCE_BACKEND=memory` (env var or `.env`) to run the container
with zero database dependency, same as the local-venv path. Full detail on
what's Postgres-backed vs. still in-memory: `docs/persistence.md`.

Example request:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/incidents/evaluate \
  -H "Content-Type: application/json" \
  -d '{
    "incidentId": "INC-101", "towerId": "T-Delhi-101", "region": "Delhi",
    "affectedUsers": 15000, "vipCustomersAffected": true, "networkLoad": 94,
    "slaTier": "Gold", "maintenanceWindow": false, "weatherSeverity": "Moderate",
    "historicalFailures": 4, "incidentType": "Tower Down"
  }'
```

## Challenges faced building this

- **The original folder structure and `tradeoffs.md` had drifted from the
  actual design doc.** A dedicated architecture review (`docs/architecture-review.md`)
  caught real gaps before implementation: the Context Aggregation Layer was
  named in `tradeoffs.md` #10 but had no module; there was no `jobs/`/scheduler
  layer even though the SLA-breach sweep and escalation chain are
  fundamentally time-based background processes, not request handlers;
  `manual_overrides` and `escalation_events` had schema tables but no domain
  entities or use cases; and three `tradeoffs.md` entries (#4 conflict
  resolution, #12 rule versioning, #13 confidence score) described a simpler
  system than the one already committed to elsewhere, which would have been
  an obvious inconsistency to any reviewer reading both documents.
- **Conflict resolution needed two different signals, not one.** A single
  categorical `priority` field can't both give a deterministic hard-stop for
  safety-critical rules *and* rank triage urgency continuously -- summing
  scores for priority would let a Critical-band incident whose individual
  signals only add up to 40 points get diluted below rules that shouldn't
  outrank it. The fix was keeping categorical `priority` (weight/specificity/
  recency resolved) and an additive `riskScore` banding as two parallel
  outputs instead of collapsing them into one.
- **The hand-traced INC-101 walkthrough in the design doc was wrong.**
  Running the exact example through the real engine surfaced that
  `networkLoad: 94` and `historicalFailures: 4` legitimately also trigger
  R012 (congestion) and R009 (chronic failures) -- both missing from the
  original manual trace. `test_inc_101_matches_expected_rules` now locks in
  the corrected, actually-computed behavior instead of the documented one,
  which is exactly the kind of drift a fixture-backed test catches before it
  reaches a demo.
- **`httpx.post()`'s module-level function has no `transport` parameter.**
  The first draft of the AI providers called it directly, which is fine in
  production but made them impossible to test without a live LLM endpoint --
  `httpx.MockTransport` only plugs into `httpx.Client(transport=...)`. Fixed
  by having each provider construct its own `httpx.Client` and accept an
  optional injected transport, so the real HTTP-call/JSON-parsing/error-
  handling code paths are exercised in tests, not just mocked around.
- **A Clean Architecture layering violation slipped in and worked anyway.**
  `ExplainDecisionAIUseCase` initially imported a serializer from the
  interfaces layer -- application depending on interfaces inverts the
  dependency rule, even though it happened not to cause a circular import at
  runtime. Fixed by having the use case build its own small local dict
  instead of reaching outward for a coincidentally similar-shaped function.
  Easy to miss exactly because it worked.
- **Cache invalidation on rule-pack activation is TTL-based, which means a
  propagation-delay window is a real, accepted tradeoff, not an oversight** --
  worth stating explicitly (10s TTL) rather than leaving it implicit, since a
  rule pack published *in response to an active incident storm* is the worst
  possible moment for different replicas to be evaluating against different
  rule-pack versions.
- **No live LLM endpoint was reachable in the build environment at all**
  (no outbound network access), which forced building `StubAIProvider` as a
  real, fully-tested implementation first, and designing every LLM-backed
  provider against the exact same interface with an injectable transport --
  so the entire AI-assisted authoring feature has full test coverage despite
  never once calling a real model during development.

## One thing this build already caught

Running the exact INC-101 example from the problem statement through the real
engine surfaced that `networkLoad: 94` and `historicalFailures: 4` legitimately
also trigger R012 (congestion) and R009 (chronic failures) -- both were left
out of the hand-traced walkthrough in `decision-engine-design.md` §5. The test
suite (`test_inc_101_matches_expected_rules`) asserts the corrected, actually-
computed behavior. This is exactly the kind of drift a fixture-backed test
harness exists to catch before it reaches a demo.

## Next build steps, in order

1. `infrastructure/database/` + `alembic/` -- wire `schema.sql` for real,
   implement a `PostgresRuleRepository` behind the existing `RuleRepository`
   interface.
2. `UnitOfWork` so a decision + its audit trail commit atomically.
3. Context Aggregation Layer -- one adapter per source under
   `infrastructure/external/`, fanned out with per-source timeout/fallback.
4. `jobs/` -- SLA-breach sweep, escalation sweep, shadow-mode diff runner.
5. `validate_rule_pack` / `promote_to_shadow` / `rollback_rule_pack` /
   `override_decision` / `acknowledge_escalation` use cases + their entities.