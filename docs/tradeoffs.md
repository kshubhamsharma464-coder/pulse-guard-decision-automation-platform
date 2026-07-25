# Tradeoffs.md

This is the corrected version of the architecture tradeoffs doc. Three entries
in the original draft (#4, #12, #13) described a simpler system than the one
actually specified in `docs/decision-engine-design.md` and implemented in
`app/`; they're fixed here, with the discrepancy noted so it doesn't silently
happen again. Four entries (#24-27) were missing outright -- these cover the
mechanisms that differentiate this from a generic rules engine and deserved
their own line. Full reasoning for all of this lives in `docs/architecture-review.md`.

## 1. Database Choice

| Option | Pros | Cons |
|---|---|---|
| JSON Files | Very simple, fast for prototypes | No concurrent updates, poor versioning, no transactions, not scalable |
| YAML | Human-readable | Parsing overhead, difficult runtime updates |
| MongoDB | Flexible schema | Loses strong ACID guarantees, joins, and version consistency |
| PostgreSQL + JSONB | Dynamic schema, ACID, indexing, transactions, versioning | Slightly more complex schema |

**Decision: PostgreSQL + JSONB.** Rules change frequently but still require transactional updates, version history, rollback, concurrent access, indexing, and audit. JSONB provides flexibility while PostgreSQL provides enterprise reliability. Schema: `app/infrastructure/database/schema.sql`.

## 2. Rule Storage

- Hardcoded if-else -- rejected, requires deployment for every business rule change.
- JSON in Git -- rejected, runtime updates impossible.
- **Database rule packs -- chosen.** Dynamic activation, version history, rollback, runtime updates. Currently fixture-backed (`app/infrastructure/data/rules-seed.json` via `InMemoryRuleRepository`) as the proven-first step per `docs/architecture-review.md` §5; a `PostgresRuleRepository` behind the same `RuleRepository` interface is next.

## 3. Rule Evaluation Strategy

- First match wins -- fast, but hides conflicts and may ignore a more important rule.
- **Evaluate all rules -- chosen.** Full explainability, conflict resolution, confidence calculation. Business systems care more about correctness than microseconds. Implemented in `app/domain/services/policy_engine.py`.

## 4. Conflict Resolution

- First rule -- simple, unpredictable. Rejected.
- **Highest priority wins -- chosen for the categorical `priority` field.** Predictable, easy to explain, and required for safety-critical rules to behave as hard stops.
- **Weighted/additive score -- chosen, but as a second, parallel signal, not instead of the above.** Every matched rule contributes a `contributionScore`; the sum is banded into LOW/MEDIUM/HIGH/CRITICAL as `riskScore`, used for triage ranking across a queue of same-priority incidents. This is **not deferred to "future enhancement"** -- it's implemented now (`app/domain/services/risk_scorer.py`, `contribution_score` column in `schema.sql`). It's deliberately kept separate from the categorical `priority` because an emergency-services incident whose individual signals sum to only 40 points must still be Critical -- summation would dilute a hard stop. Score ranks; category decides.

## 5. Runtime Rule Updates

- Restart application -- simple, but downtime. Rejected.
- **Cache refresh -- chosen.** Rule Activated → Database → Cache Invalidated → Reload → Next Request Uses New Rule. No downtime. See #17 for the propagation-delay tradeoff this implies under horizontal scaling.

## 6. Explainability

- Return only the decision -- rejected. Business users need to know why, which rule, which condition, why a rule was rejected, and how confident the platform is.
- **Chosen: evaluation tree, trace, and narrative.** `app/domain/services/explainability_builder.py` builds a human-readable explanation plus matched/rejected/suppressed rule traces on every decision.

## 7. Rule Operators

- Huge switch statement -- rejected, every new operator changes the engine.
- **Strategy pattern / plugin registry -- chosen.** `app/engine/evaluators/` implements `var`, `and`, `or`, `==`, `>`, `<`, `>=`, `<=`, `in` as independently registered evaluators (`evaluator_factory.py`). New operators (regex, date, geo) register without touching the dispatcher -- Open/Closed. Note: only the operators the 35 seeded rules actually use are implemented and tested right now; regex/date/geo are documented extension points, not yet exercised by any rule or test.

## 8. Rule Packs

- Single rule table -- rejected, business domains differ (telecom, insurance, fraud, healthcare) and need isolation.
- **Chosen: Rule Packs**, scoped by `region`/`tenant_id` (`rule_sets` table). Nothing in `app/engine/` or `app/domain/` references telecom by name -- a rule pack swap is how this becomes an insurance-claims or fraud-scoring platform.

## 9. Decision History

- Overwrite decisions -- rejected, business requires audit, compliance, analytics, and historical replay.
- **Chosen: immutable decision history.** Every evaluation produces a new `decisions` row; a context change after incident creation produces a new, linked decision rather than mutating the original (design doc §7).

## 10. Historical Context

- Ignore history -- rejected, decisions improve when context exists (e.g. "tower failed 3 times today → escalate").
- **Chosen: Context Aggregation Layer.** 14 named source systems (weather, CRM, SLA, power grid, security alerting, vendor KB, workforce, etc.), each with its own timeout and fallback (design doc §2). **Not yet built** -- the current API accepts a `context` object directly in the request in its place; this is the top structural gap called out in `docs/architecture-review.md` §2 and the next major build item.

## 11. API Design

- Single endpoint -- rejected.
- **Chosen: purpose-specific endpoints** -- evaluate, rules, rule packs, simulation, health, metrics. Currently implemented: `POST /api/v1/incidents/evaluate`, `GET /health`. Rule/rule-pack CRUD, simulation, and metrics endpoints are not yet built.

## 12. Rule Versioning

- Update in place -- rejected, makes it impossible to reproduce old decisions.
- **Chosen lifecycle: `Draft → Validated → Shadow → Active → Deprecated → Rolled back`.** Every decision stores the exact rule-set version evaluated (`rule_set_version_used`). The **Shadow** stage is load-bearing, not optional: it's what lets a candidate rule pack run against real traffic in parallel with production and get diffed before promotion (design doc §8) -- the safety net that answers "how do you stop a bad rule change from reaching production." A simplified `Draft → Published → Deprecated → Rollback` lifecycle without Shadow would quietly drop that guarantee; the six-state version above is the one to build.

## 13. Confidence Score

- Random/AI-generated score -- rejected, business decisions must be deterministic.
- **Chosen: `confidence_score` = fraction of context sources that returned live data vs. fell back to a default** (`app/domain/services/confidence_calculator.py`, design doc §6/§9 edge case 28). This is a **data-completeness** signal ("can I trust the inputs?"), deliberately **not** the same thing as "how strong is the rule consensus behind this decision" (which would be derived from rule weights/match count/business impact). Those are two different, both-useful numbers; if the second one is wanted too, it needs its own field name (e.g. `decisionStrength`) rather than overloading `confidence_score`.

## 14. AI Usage

- AI makes the decision -- rejected. Business decisions must be deterministic, auditable, and reproducible.
- **Chosen: AI assists, rules decide.** Rule generation, documentation, explanation, and testing can be AI-assisted; a proposed rule is just JSON and goes through the same `Draft → Shadow` pipeline as a human-authored one (design doc §10).

## 15. Scalability

- Stateful service -- rejected.
- **Chosen: stateless API, horizontal scaling, shared PostgreSQL, cache layer.** See #17 for what this implies about rule-pack cache propagation across replicas.

## 16. Runtime Configuration

- Environment restart -- rejected.
- **Chosen: database-driven configuration, zero downtime.** (Overlaps with #5 -- both describe the same underlying mechanism from different angles; kept as separate entries because reviewers tend to ask about them separately.)

## 17. Caching

- Always read PostgreSQL -- always latest, but slow.
- **Chosen: active rule-pack cache, database remains source of truth, refreshed after activation.** The cache-invalidation propagation-delay question flagged in the first draft is now decided rather than left open: **push-based invalidation is primary, a short TTL is the fallback safety net.** `RulePackRepository.activate()` calls `TTLCache.invalidate()` synchronously (`app/core/cache.py`); in a multi-replica deployment the same activation event is published over Postgres `LISTEN/NOTIFY` so every replica invalidates immediately instead of each waiting out its own TTL. The TTL (10s) exists only to cover a replica that missed the notification -- e.g. reconnecting after a network blip -- not as the primary mechanism. It's deliberately short because the scenario that matters most here (R017, a rule pack published *in response to an active incident storm*) is exactly the moment a multi-second propagation gap is least acceptable. Under horizontal scaling (#15) this means: normally near-zero propagation delay, worst case ≤10s for a replica that missed the push.

## 18. Logging

- Console logs -- rejected.
- **Chosen: structured JSON logging**, containing request ID, correlation ID, execution time, decision ID, and rule-pack version. Recommend also including matched rule codes, `risk_score`, and `confidence_score` for faster triage directly from the log stream, plus `tenant_id`/`region` once multi-tenancy is live.

## 19. Error Handling

- Generic 500 -- rejected.
- **Chosen: domain / validation / repository / infrastructure exception hierarchy.** Every error is actionable. (`app/core/exceptions.py`, not yet implemented -- current MVP relies on FastAPI's default error handling.)

## 20. Authentication

- No authentication -- rejected.
- **Chosen: JWT, RBAC-ready, bearer tokens for machine clients.** Ties to `audit_log.actor` being required on every write. Not yet implemented in the current build.

## 21. Business Tradeoff

A fully dynamic rule engine can become difficult for non-technical users to manage if rules are too expressive (deep nesting, complex logic). We deliberately support nested conditions and extensible operators but keep rule authoring JSON-based for this stage. In a production platform, a visual rule builder with validation, approvals, and governance would reduce operational risk.

## 22. Performance Tradeoff

Evaluating every applicable rule provides maximum explainability but increases latency versus stopping at the first match. We intentionally evaluate all rules because telecom operational decisions require transparency and auditability, accepting a small latency cost for deterministic outcomes, conflict detection, and complete execution traces.

## 23. Extensibility Tradeoff

A plugin-based evaluator architecture was chosen over a monolithic implementation. This introduces more abstraction and initial complexity but allows new rule operators (geospatial, ML score, regex) to be added without modifying the core engine, reducing long-term maintenance cost.

## 24. Suppression vs. Self-Veto vs. Compliance Constraint

Three distinct mechanisms exist on the same `Rule` entity, and it would have been simpler to have just one. They're kept separate because they answer different questions: a **suppressor** (`is_suppressor`) is a full rule that fires, wins a contested field, and can itself be overridden by a `non_suppressible` rule ("should this maintenance window silence the dispatch?"); an **exception** (`exceptions` clause) is a self-veto that removes a rule from consideration before it ever competes ("should this rule even be a candidate, given it's a known duplicate?"); a **compliance constraint** (`family: COMPLIANCE`) never competes for priority at all, and runs after conflict resolution to narrow how the winning decision executes ("regardless of what won, this traffic can't leave the region"). Collapsing these into one mechanism would make at least one of the three cases inexplicable in the audit trace. Implemented in `conflict_resolver.py`, `policy_engine.py`, and `compliance_applier.py` respectively.

## 25. Execution Plan / Sequencing vs. Flat Parallel Actions

A flat OR-merge of boolean actions (`dispatchEngineer: true`) can't express "try a remote restart first, fall back to dispatch after 15 minutes if it doesn't resolve" -- that needs an ordered plan with retry semantics. We accepted the added complexity of a `sequencing` hint per rule and an `ExecutionPlanBuilder` (design doc §3d) because a flat action dict is a label an ops console has to interpret, while an ordered plan is something it can directly drive.

## 26. Manual Override: Append-Only vs. In-Place Mutation

An operator overriding the platform's recommendation never overwrites the automated decision record. `manual_overrides` is a separate table referencing the original decision, storing both the `original_decision` snapshot and the operator's `override_decision` plus a mandatory reason. This costs an extra table and join versus just updating `decisions.decision` in place, but it's what makes "the engine was right and an operator had situational information it didn't" distinguishable from "the engine was wrong" after the fact -- which is the whole audit-trail selling point of this platform.

## 27. Escalation as a Background Sweep vs. a Synchronous Rule

Escalation fires on acknowledgment *silence* -- a responder not acting within N minutes -- which structurally cannot be expressed as a JsonLogic condition on the incident payload (there's no incident field for "time since assignment with no ack"). We modeled it instead as an `escalation_policies` + `escalation_events` pair evaluated by a scheduled sweep, not a rule. This is also why a `jobs/`/scheduler layer belongs in the architecture alongside the request-driven API, not as an afterthought.

---

## Final Architectural Decision

If a Deutsche Telekom architect asks, *"Why did you design it this way?"*, the answer is:

> "We optimized for deterministic decision-making, operational transparency, and long-term maintainability rather than minimizing implementation effort. Every architectural choice favors runtime configurability, auditability, explainability, and extensibility. The platform is intentionally stateless, rule-driven, and domain-agnostic so it can evolve from telecom incident prioritization to other enterprise decision domains with minimal code changes. We accepted modest increases in architectural complexity where they significantly reduced future operational and maintenance costs -- and where we haven't built a piece yet (Postgres persistence, the context aggregation layer, background jobs, auth), we've said so explicitly rather than let the documentation imply it already exists."
