# Simulation Engine + Bulk Evaluation -- Phase 4

What-if analysis, historical replay, rule-version comparison, and bulk
evaluation with aggregate metrics -- all built on top of the exact same
`PipelineOrchestrator`/`EvaluateIncidentUseCase` the real, production
`POST /api/v1/incidents/evaluate` path uses. Nothing here is a second,
approximate decision engine wearing a simulation's name: the same code
runs either way, only what it's pointed at (which rule pack) and whether
it persists differ.

## Why this matters: trustworthy simulation

A simulation whose result can't be trusted to match what production would
actually do is worse than no simulation at all -- it gives false
confidence. Every use case in this phase is built to make divergence
structurally impossible rather than just "tested to currently agree":

- `WhatIfSimulationUseCase`, `ReplaySimulationUseCase`, and
  `CompareRulePacksUseCase` all take a `PipelineOrchestrator` instance as
  a constructor argument, and `dependencies.py` passes them
  `evaluate_incident_use_case.orchestrator` -- the literal same object
  instance the real evaluation endpoint runs, including its
  `SlaMatrixLookup` wiring. There's no second orchestrator anywhere in
  this phase.
- `BulkEvaluateUseCase` doesn't even have its own evaluation logic --
  `persist=true` calls the real, already-persisting
  `EvaluateIncidentUseCase` per item; `persist=false` calls a second
  `EvaluateIncidentUseCase` instance built with the same rule repository,
  orchestrator, and context-aggregation service, differing only in having
  no `DecisionRepository` attached. Same pipeline, same context
  aggregation, the only difference is a write at the very end.

## Which rule pack? (`rule_pack_resolution.py`)

Every simulate/replay/compare request accepts an optional rule-pack
reference: `rulePackId` (an exact versioned pack, including a Draft that
was never activated), or `rulePackName`(+`rulePackVersion`). Omitting all
three falls back to `RuleRepository.get_active(region, tenant)` -- the
SAME source `POST /api/v1/incidents/evaluate` reads from (the static
142-rule fixture composite by default, or the cache-fronted Postgres rule
set with `RULE_SOURCE=dynamic`). This is what makes "simulate against
production" mean the same thing simulation says it means, and what makes
"simulate against this draft I haven't published yet" possible without
activating it first just to test it.

Every response includes a `rulePackUsed` block (`{source, id, name,
version, status, region}`) so a caller never has to trust silently which
pack was actually evaluated against.

## Endpoints (tag "Simulation" / "Decisions")

### `POST /api/v1/simulate` -- what-if

Runs one incident payload (same shape as `POST /api/v1/incidents/evaluate`)
through the pipeline against the resolved rule pack. Never persists
anything -- no incident record, no decision, no audit entry. Requires
`simulation:run`.

### `POST /api/v1/simulate/replay` -- historical replay / impact analysis

Takes `incidentId` for an already-persisted incident (created via
`POST /api/v1/incidents` or `/evaluate`), re-runs its exact original
payload against the resolved rule pack, and diffs the result against the
most recent decision on record for that incident (`decisions:read`'s
`GET /api/v1/decisions/{id}` data, read internally). Returns `differs`
and a human-readable `differences` list (priority change, risk-band
change, matched-rule set change, action-field changes). Read-only: the
original incident and decision are never modified -- this answers "if
this incident came in today, would the outcome change?" without touching
history. 404 if the incident id doesn't exist. Requires `simulation:run`.

### `POST /api/v1/simulate/compare` -- rule-version comparison

Runs a batch of incidents (`incidentIds` to replay, and/or inline
`incidents` payloads) through two rule packs -- a `baseline` (defaults to
the active hot-path pack) and a required `candidate` -- and reports where
they disagree (`differingCount` out of `totalIncidents`, plus a per-
incident diff). Capped at `Settings.simulation_max_compare_incidents`
(default 200) incidents per request.

Deliberately a separate use case from the pre-existing
`PromoteToShadowUseCase` (`promote_to_shadow.py`, Phase 1's shadow-mode
validation flow), not a generalization of it: promotion is a gated
workflow step that requires the candidate to pass
`ValidateRulePackUseCase` and mutates the candidate's status to
`"shadow"` as a side effect -- existing tests already depend on that
exact behavior. `CompareRulePacksUseCase` is a pure, read-only analysis
tool with no validation gate and no status mutation, usable at any time
against any two pack references (an editor comparing two of their own
drafts, not just "is this draft ready to promote").

### `POST /api/v1/evaluate/bulk` -- bulk evaluation

Evaluates many incidents in one request with per-item error isolation --
one malformed incident doesn't abort the rest of the batch, it's counted
as a failure with its error message instead. `persist: true` (default)
saves every successful decision exactly like the single-incident endpoint
would; `persist: false` is a pure dry-run bulk simulation. Returns:

- `totalSubmitted` / `succeeded` / `failed`
- `priorityDistribution` / `riskBandDistribution` (counts across the
  batch's successful decisions)
- `executionTimeMs` / `averageTimeMsPerIncident`
- `results`: per-incident `{incidentId, success, priority, riskBand,
  error}`

Capped at `Settings.bulk_evaluate_max_items` (default 2000) incidents per
request -- above that, `422` rather than an unbounded-time request.
Requires `incidents:evaluate` (the same permission the single-incident
endpoint requires -- bulk is the same operation, just batched).

### `GET /api/v1/decisions/distribution` -- decision analytics

Aggregate counts (`priorityDistribution`, `riskBandDistribution`),
`averageRiskScore`, `averageConfidenceScore`, and `degradedContextCount`
over the most recent `limit` (default 10,000, max 50,000) persisted
decisions, newest first. Registered on `decision_router.py` *before* the
`GET /{incident_id}` path-parameter route specifically so `"distribution"`
is never accidentally matched as a literal incident id -- route
registration order matters in FastAPI/Starlette, and this is exactly the
kind of ordering bug that's easy to introduce silently, so it's called
out here and covered by
`test_decisions_distribution_route_is_not_shadowed_by_incident_id_route`.
Requires `decisions:read`.

The aggregation itself lives in `DecisionDistributionUseCase`
(application layer), not pushed into `DecisionRepository` -- the
repository's new `list_all(limit, offset)` method (added to the
`DecisionRepository` interface and both `InMemoryDecisionRepository` and
`PostgresDecisionRepository`) is a plain, backend-agnostic read; the
counting/averaging logic is identical regardless of which backend is
behind it.

## Schema note: no new tables, no new migration

Phase 4 required no new database tables or columns -- `list_all()` reads
the existing `decisions` table via its existing `created_at` column, and
every simulate/replay/compare use case reads through the existing
`RuleRepository`/`RulePackRepository`/`IncidentRepository`/
`DecisionRepository` interfaces. `migrations/` is unchanged from `0003`.

## RBAC

One new permission, `simulation:run`, covering all three read-only
`/api/v1/simulate*` endpoints (`admin`, `operator`, `editor`, and
`policy_admin` all have it; `viewer` doesn't -- consistent with every
other write-adjacent capability being denied to the read-only role, even
though simulation itself never writes). `POST /api/v1/evaluate/bulk`
reuses the pre-existing `incidents:evaluate` permission rather than
introducing a separate one, since it's the same operation as the
single-incident endpoint, just batched.

## Verification performed

- Full regression: 196 passed (175 pre-existing + 20 new HTTP/use-case
  tests in `tests/test_simulation_api.py` + 1 new Postgres round-trip
  test for `DecisionRepository.list_all`), zero changes to any
  pre-existing test file.
- Manually smoke-tested every endpoint via `TestClient` before writing
  formal tests: what-if against the active pack and against an explicit
  Draft pack id, replay of a persisted incident (both matching and
  diverging from its original decision), compare with inline incidents
  and with persisted `incidentIds`, bulk evaluate with `persist=true`/
  `false` and a structurally-invalid item, and the distribution endpoint
  before/after new evaluations.
- `test_bulk_evaluate_use_case_isolates_per_item_failures` exercises
  failure isolation directly against `BulkEvaluateUseCase` with a
  fault-injecting fake use case, since a structurally-invalid HTTP
  payload (e.g. a missing `incidentId`) is instead caught by Pydantic
  before it ever reaches the use case -- a different, already-covered
  422 failure mode, not per-item isolation.
- Cap enforcement (`simulation_max_compare_incidents`,
  `bulk_evaluate_max_items`) is tested directly against the use cases
  with a small cap rather than constructing hundreds/thousands of HTTP
  payloads to hit the real production default -- cheaper and exercises
  the identical cap-check code path either way.
