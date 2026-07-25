# External rule packs -- integration record

Five externally-authored rule packs, each in its own distinct JSON schema,
have been merged additively on top of the original 35-rule `rules-seed.json`.
This document is the single place that explains how, why they can't have
broken anything that existed before them, what's a documented
simplification rather than an oversight, and (for the sixth pack) which
source rules were deliberately not loaded because they duplicated existing
coverage.

The standing constraint for all integrations, restated as given: the
existing 35-rule pack, the existing engine (`app/engine/`), and the existing
domain services (`PolicyEngine`, `ConflictResolver`, `RiskScorer`,
`ComplianceApplier`, `ExecutionPlanBuilder`, `ExplainabilityBuilder`) must
require **zero changes** to accept a new pack. Every pack below is proof of
that: each is a data file plus one adapter module that transpiles it into
the same canonical `Rule` dataclass everything else already understands.

## The five packs

| Pack | File | Source rule count | Loader | Native rules produced |
|---|---|---|---|---|
| SLA telecom pack | `customer_sla_rules_telecom.json` | 8 (`SLA-RULE-xxx`) | `sla_rule_pack_loader.py` | 12 (SLA-RULE-002's `weightTable` expands into 5 tier rules) |
| Generic customer-workflow pack | `customer_sla_rules_vast.json` | 30 (`CSR-xxx`) | `vast_rule_pack_loader.py` | 30 |
| Customer/SLA priority-decision pack | `csr_sla_decision_rules.json` | 18 (`CSR-SLA-xxx`) | `csr_sla_rule_pack_loader.py` | 18 |
| Historical/operational-pattern pack | `telecom_incident_decision_engine_rules.json` | 30 (`HIS-xxx`) | `historical_pattern_rule_pack_loader.py` | 30 |
| Network/infrastructure pack | `telecom_network_infrastructure_rules.json` | 20 (`NET-INF-xxx`) | `net_inf_rule_pack_loader.py` | 14 (6 of the 20 source rules are skipped as duplicates -- see below) |

Total after merge: 35 + 12 + 30 + 18 + 30 + 14 = **139 rules**, all evaluated
together in one `PolicyEngine`/`ConflictResolver` pass via
`CompositeRuleRepository`
(`app/infrastructure/repositories/composite_rule_repository.py`), wired only
in the API's composition root (`app/interfaces/api/dependencies.py`). No test
in `tests/conftest.py` uses `CompositeRuleRepository` -- they all still
construct a bare `InMemoryRuleRepository()`, which is untouched and still
returns exactly the original 35 rules.

## Why an adapter, not a schema unification

Each source pack was authored independently, in a different shape
(`conditions`/`logicalOperator`/`onMatch`; `when.all`/`when.any` with
`{field, op, value}`; a raw JsonLogic `when` tree with an `incident.` var
prefix). Rather than write one mega-parser that understands three schemas,
or worse, rewrite the source files into "the" canonical format (which would
make re-syncing a future update from whoever owns each source file a manual
diff exercise), each pack gets its own small, readable loader whose only job
is: read the file, produce `Rule` objects. `PolicyEngine` and everything
downstream only ever sees `Rule` -- they have no idea any of this exists.

## Pack 1 -- SLA telecom pack (`sla_rule_pack_loader.py`)

- SLA-RULE-008 (emergency/regulatory) -> `SAFETY_REGULATORY` family, weight
  100, `non_suppressible=True`, `contribution_score=None` (bypasses additive
  scoring, same reasoning as `tradeoffs.md` #4: safety-critical rules must
  never be diluted by summation with unrelated contributors).
- SLA-RULE-001 (Platinum critical) -> `CUSTOMER_VALUE`, weight 88,
  `contribution_score=None`.
- SLA-RULE-002 (tier base weight) -> expands into 5 rules
  (`SLA-RULE-002-PLATINUM/GOLD/SILVER/BRONZE/RESIDENTIAL`), modifier-only
  (no `priority` action, never enters the priority conflict group).
- SLA-RULE-003 -> `NETWORK_IMPACT` modifier.
- SLA-RULE-004 -> uses the new `*` operator for the dynamic threshold
  `minutesSinceIncidentOpened >= slaResponseMinutes * 0.8`; maps to
  `priorityBumpOneLevel` + `slaBreachImminent` (a nudge, not a hard override
  -- the source labels it ESCALATE but carries a `weight`, not a
  `priorityScore`).
- SLA-RULE-005/006 -> simple modifiers.
- SLA-RULE-007 (maintenance suppression) -> `SUPPRESSION` family,
  `is_suppressor=True`, `conflict_group="dispatch-suppression"` (same group
  as the original R011/R010/R018/R033/R022/R026), uses the new `!=` operator
  for the Platinum exclusion.
- `SlaMatrixLookup` (`app/domain/services/sla_matrix_lookup.py`) is a
  separate, optional fill-in step wired into `PipelineOrchestrator` right
  after `ComplianceApplier`: if no rule already set `targetSLA`, it resolves
  one from the pack's `slaMatrix` by customer tier + resolved priority.
  Optional constructor parameter, defaults to `None` -- orchestrators built
  without it behave exactly as before.

## Pack 2 -- generic customer-request-workflow pack (`vast_rule_pack_loader.py`)

This pack is a different decisioning vertical (approve/deny/escalate a
customer request, not a telecom incident), so rather than force its 30 rules
into the existing 8 telecom families, they get one new family,
`CUSTOMER_REQUEST_WORKFLOW`, and one shared `conflict_group`,
`customer-decision` (all 30 write the same two action fields,
`customerDecision`/`customerAction`).

Two new operators were added to the engine to support it: `contains`
(haystack, needle convention -- `{"contains": [{"var": "tags"}, "vip"]}`)
and `in_holiday_period`, added as an honestly-documented **stub**: it reads
the referenced field's own truthiness and ignores the literal `value`
operand. A real calendar lookup would replace only that evaluator's body
(`app/engine/evaluators/reference_lookup.py`) -- no other file would need to
change.

Flagged deviation (not a mechanical transpile step): **CSR-021** (fraud-risk
block, source priority 100) ties with **CSR-001** (enterprise-priority
approve, also priority 100). The existing tiebreak (equal specificity, then
`rule_code` ascending) would let `CSR-001` beat `CSR-021` alphabetically --
i.e. a high-fraud-risk enterprise customer would see "approve/escalate" win
over "deny/block". `CSR-021`'s `priority_weight` is bumped from 100 to 105
in the loader to give the fraud block an unambiguous, deterministic win.
This is a value judgment call, not a mechanical fact extracted from the
source file, and needs real business sign-off before being treated as final.

## Pack 3 -- customer/SLA priority-decision pack (`csr_sla_rule_pack_loader.py`)

18 rules (`CSR-SLA-001`..`018`), ruleSetId `telecom-customer-sla-rules`.
Unlike the other two, this pack's `when` trees are already valid JsonLogic
(`==`, `in`, `<=`, `>=` on `{"var": ...}` nodes), so no operator-translation
table is needed -- the loader uses the tree as-is.

- **Field-prefix stripping**: every var path in the source is prefixed
  `incident.` (e.g. `incident.customerTier`), a namespace
  `Incident.as_evaluation_data()` doesn't use -- that method flattens the
  raw payload straight to the top level. Rather than change the shared
  evaluation-data shape every existing rule and test depends on, the loader
  strips the `incident.` prefix recursively at load time
  (`_strip_incident_prefix`), so these conditions resolve against the same
  flat fields every other rule already reads. This is read-only reuse of
  field names like `customerTier` (also read, with different casing
  conventions, by the SLA telecom pack) -- safe, because only concurrent
  *writes* to a shared field need isolation.
- **Action-field namespace**: all 18 rules write the same six fields --
  `decision`, `csrSlaAction`, `escalationTarget`, `csrSlaPriorityScore`,
  `csrSlaConfidence`, `csrSlaExplanation`. Checked by grep against the rest
  of the codebase before choosing these names; the API's outer envelope key
  `decision` (in `serializers.py`, wrapping the entire `actions` dict) is a
  different concept at a different nesting level, not a collision.
- **Conflict resolution**: all 18 share one `conflict_group`,
  `csr-sla-priority-decision`, using the source pack's own 300-960
  `priority` integer directly as `priority_weight`. This reuses the existing
  weight -> specificity -> recency -> rule_code algorithm rather than adding
  pack-specific resolution logic.
- **Documented simplification**: the source pack declares
  `defaultConflictPolicy: "highest_priority_then_highest_confidence_then_newest_version"`.
  The shared resolver's tiebreak order is weight -> specificity -> recency ->
  rule_code -- there is no "confidence" stage. `confidence` is preserved in
  the output (`csrSlaConfidence`) for downstream/audit visibility but does
  not currently participate in conflict resolution; specificity is used as
  the generic secondary criterion instead, exactly as for every other pack.
- **`contribution_score` is `None` for all 18**: this pack's numeric
  `priority` (300-960) is a routing signal for its own conflict group, not a
  severity delta on the existing additive risk-scoring scale (0-120,
  banded LOW/MEDIUM/HIGH/CRITICAL). Feeding it in would silently distort the
  risk band computed for any incident this pack also matches -- exactly the
  kind of cross-pack interference the "nothing existing should break"
  constraint rules out.

## Pack 4 -- historical/operational-pattern pack (`historical_pattern_rule_pack_loader.py`)

30 rules (`HIS001`..`HIS030`), ruleSetId `telecom-incident-decision-engine`,
covering historical failure patterns, change correlation, physical
infrastructure risk, timing/sync faults, governance, and customer-impact
signals. Like the CSR-SLA pack, its `conditions` trees are already valid
JsonLogic, so no operator-translation table is needed.

- **Two different namespace conventions, each handled the way this codebase
  already handles it elsewhere**: `incident.*` var paths are stripped to
  their bare name (same convention, same `_strip_incident_prefix` pattern,
  as the CSR-SLA pack), because `Incident.as_evaluation_data()` has no
  `incident` namespace. But `asset.*`, `metrics.*`, `customer.*`, `change.*`,
  and `context.*` var paths are left as nested dotted lookups -- the same
  convention as the vast pack's `customer.segment`/`request.amount` handling
  -- since `VarEvaluator` already supports dotted paths and the caller's
  incident payload just needs to supply nested objects under those keys.
  `context.*` specifically lines up with the existing Context Aggregation
  Layer's reserved `"context"` namespace in `as_evaluation_data()`; a real
  `ContextProvider` could eventually populate `weatherSeverity`, `month`,
  `hourOfDay`, `dayOfWeek`, `isHoliday`, `gridOutageReported` there. This is
  read-only, so it's safe regardless of whether that data exists yet.
- **Var-to-var comparison** (HIS002: `incident.affectedAsset ==
  change.assetId`) is supported natively -- no engine change needed, same as
  CSR-SLA-007's `similarIncidentServiceId == serviceId`.
- **Action-field namespace, and why it matters here specifically**: all 30
  rules write the same seven fields (`decision`, `priority`, `confidence`,
  `assignmentGroup`, `escalationLevel`, `reasonCodes`, `slaBreachRisk`). Two
  of those names are *not* safe to reuse bare, even though grep confirmed no
  other pack literally uses the key `"priority"` and only the CSR-SLA pack
  uses `"decision"`: `ConflictResolver.resolve()` groups writers by field
  name **globally across all matched rules**, not scoped per pack or per
  `conflict_group` (see the class's own "known simplification" docstring).
  If this pack also wrote bare `decision`, a HIS rule and a CSR-SLA rule
  matching the same incident with different `conflict_group`s would fall
  through to `_merge_field`'s highest-priority-weight fallback and silently
  overwrite one pack's decision vocabulary with the other's. And `priority`
  is the existing categorical Critical/High/Medium/Low field used throughout
  the whole system (SLA matrix lookup, risk banding, priority floors/bumps)
  -- this pack's P1-P5 scale must never reach that key. So every action
  field here is prefixed `his`: `hisDecision`, `hisPriority`,
  `hisConfidence`, `hisAssignmentGroup`, `hisEscalationLevel`,
  `hisReasonCodes`, `hisSlaBreachRisk`. Proven, not just asserted, by
  `test_his_pack_decision_field_does_not_collide_with_csr_sla_pack_decision_field`
  in `tests/test_composite_repository_backward_compat.py`.
- **Conflict resolution**: all 30 share one `conflict_group`,
  `his-decision`, using the source pack's own 895-985 `priority` integer
  directly as `priority_weight`. `confidence` is preserved
  (`hisConfidence`) but, like the CSR-SLA pack, doesn't participate in
  conflict resolution -- the shared resolver has no confidence tiebreak
  stage, specificity is used instead.
- **`contribution_score` is `None` for all 30**, same reasoning as the
  CSR-SLA pack: this pack's numeric priority is a routing signal for its own
  conflict group, not a severity delta compatible with the existing additive
  risk-scoring scale.

## Pack 5 -- network/infrastructure pack (`net_inf_rule_pack_loader.py`)

20 rules (`NET-INF-001`..`020`), ruleSetId `telecom-network-infrastructure-rules`.
This is the first pack that is **not purely additive at the source-rule
level** -- unlike every earlier pack, several of its rules cover ground the
CSR-SLA pack already covers, sometimes with byte-identical condition logic.
Per the explicit instruction to skip what's already covered, six of the 20
source rules are deliberately **not loaded**:

| Skipped rule | Duplicates | Why |
|---|---|---|
| NET-INF-003 "Incident Reopened Quickly" | CSR-SLA-006 | Condition (`hoursSinceClosure<=48`) is a strict subset of CSR-SLA-006's `<=72`, identical decision/action/target -- adds no new coverage. |
| NET-INF-004 "Similar Incident Within One Hour" | CSR-SLA-007 | Condition byte-identical; action string differs cosmetically (`attach_to_parent_incident` vs `attach_to_existing_incident`) for the same intent. |
| NET-INF-005 "Historical Outage Frequency" | CSR-SLA-008 | Condition and decision/action/target byte-identical. |
| NET-INF-006 "Low MTBF Chronic Equipment" | CSR-SLA-010 | Condition and decision/action/target byte-identical. |
| NET-INF-009 "Maintenance Window Suppression" | CSR-SLA-012 | Condition and decision/action/target byte-identical. |
| NET-INF-011 "SLA Breach Imminent" | CSR-SLA-003 | Condition and decision/action/target byte-identical. |

All 20 source rules, including the 6 skipped ones, are still saved verbatim
in `telecom_network_infrastructure_rules.json` for provenance -- the skip is
expressed in exactly one place, `SKIPPED_RULE_IDS` in the loader, with the
reasoning inline, and is reversible (remove an entry to load that rule).

**Not skipped despite thematic overlap**, because the condition, action, or
escalation target is materially different:

- **NET-INF-002** adds an extra `mtbfHours<=72` condition on top of
  CSR-SLA-005's tower-failure condition and routes to `ran_engineering`
  instead of `engineering_oncall` -- a genuinely more specific companion
  rule (fires on a strict subset of what CSR-SLA-005 matches, with a
  different, more specialized recommendation), not a duplicate.
- **NET-INF-010** shares CSR-SLA-013's exact condition (unapproved
  maintenance with customer impact) but **disagrees** on `escalationTarget`
  (`engineering_oncall` vs CSR-SLA-013's `noc_level_3`). This is a genuine
  cross-pack policy disagreement on the same trigger, not a duplicate to
  silently pick a winner for -- surfaced the same way the vast pack's
  CSR-021/CSR-001 tie was surfaced, except here neither side is silently
  overridden: both packs' recommendations remain independently visible in
  the decision output (`escalationTarget` from CSR-SLA-013,
  `netInfEscalationTarget` from NET-INF-010), for a human to reconcile.
- **NET-INF-016, 018, 019** reuse a CSR-SLA action name (`priority_business_review`,
  `standard_priority_queue`, `engineering_root_cause_review` respectively)
  but key off different fields or thresholds entirely (`customerSegment`
  instead of `isOpen`; `mttrHours` vs `impactScope`; `equipmentFailures30d`
  vs `repeatFailures90d`) -- different triggering logic, kept as
  independent rules rather than assumed redundant just because the action
  name matches.

**Action-field namespace, and why it's not optional this time**: the CSR-SLA
pack already writes bare `decision` and `escalationTarget` action keys.
`ConflictResolver.resolve()` groups writers by field name **globally across
all matched rules**, regardless of pack or `conflict_group` -- if NET-INF
also wrote those bare keys, NET-INF-010 and CSR-SLA-013's disagreement on
`escalationTarget` (same condition, different intended value) would make one
pack's routing recommendation silently overwrite the other's on any incident
that trips both. So every NET-INF output field is prefixed `netInf`:
`netInfDecision`, `netInfAction`, `netInfEscalationTarget`,
`netInfPriorityScore`, `netInfConfidence`, `netInfExplanation`. Proven by
`test_net_inf_and_csr_sla_disagreement_stays_independently_visible` in
`tests/test_composite_repository_backward_compat.py`.

Family: `NETWORK_INFRASTRUCTURE_PATTERN` (family_order 13). Conflict group:
`net-inf-decision`, shared by all 14 loaded rules, weight = source
`priority` (100-1000). `contribution_score` is `None` for all 14, same
reasoning as the CSR-SLA and HIS packs.

## Known, deliberate field-namespace overlaps (not reconciled)

Several packs read differently-named fields for what is conceptually the
same real-world attribute:

- Customer tier: `slaTier` (base pack) vs `customerTier` (SLA + CSR-SLA
  packs, and note SLA pack expects `PLATINUM`/`GOLD` uppercase while CSR-SLA
  expects `gold`/`platinum`/`enterprise` lowercase) vs `customer.segment`
  (vast pack, nested).
- Maintenance window: `maintenanceWindow` (base pack) vs
  `isDuringPlannedMaintenance` (SLA pack) vs `inMaintenanceWindow`
  (CSR-SLA pack).
- Emergency/regulatory: `emergencyServicesAffected` (base pack) vs
  `isEmergencyServiceLine` (SLA pack).
- Affected scale: `affectedUsers` (base pack) vs `affectedCustomerCount`
  (SLA pack).

These are left as separate fields on purpose. Aliasing them together would
be a real behavior-changing risk (an incident payload using the base pack's
field name could suddenly also trigger a differently-scoped rule from
another pack), and it can't be done safely without a canonical field
dictionary and a real data-contract decision with whoever owns each pack.
Tracked as explicit future work, not silently patched over.

## Also not implemented (carried over from the SLA pack's own doc gap)

- **Explanation/reason templates aren't substituted.** `explainability_builder.py`
  builds its human-readable text from each matched rule's `.name`, not from
  the source packs' own `reason`/`explanation`/`response_template` strings
  (which contain `{field}`-style placeholders in the vast pack). The raw
  template text is preserved on the `Rule.description`/`actions` fields for
  API consumers, but no substitution engine exists yet.
- **`in_holiday_period` is a stub**, as noted above.

## Verification performed

- Full regression suite (`pytest tests/ -q`): 77 passed (35 original +
  4 new-operator tests + 7 SLA-pack tests + 6 vast-pack tests + 6 CSR-SLA-pack
  tests + 6 HIS-pack tests + 7 NET-INF-pack tests + 6 composite-repository
  backward-compatibility locks), zero failures, zero changes to any
  pre-existing test file.
- `tests/test_composite_repository_backward_compat.py` proves, as executable
  tests rather than assertions in prose: (1) a bare `InMemoryRuleRepository()`
  still returns exactly 35 rules; (2) the exact INC-101 problem-statement
  payload, run through the fully-merged 139-rule `CompositeRuleRepository`,
  still matches exactly `{R001, R004, R007, R009, R012}` and still resolves
  to `Critical` priority -- identical to the pre-merge baseline; (3) the
  CSR-SLA pack's conflict resolution deterministically picks the
  higher-weight rule on a genuine multi-match; (4) the HIS pack's own
  conflict resolution does the same; (5) the CSR-SLA pack's `decision` field
  and the HIS pack's `hisDecision` field coexist without either overwriting
  the other; (6) the NET-INF pack's `netInfEscalationTarget` and the CSR-SLA
  pack's `escalationTarget` independently disagree on NET-INF-010 vs
  CSR-SLA-013 without either being silently overwritten.
- Live smoke test through the actual FastAPI app (`TestClient`, not just unit
  tests) for the INC-101 regression case, a CSR-SLA scenario (SLA breach +
  Gold customer major impact), a HIS scenario (fiber cut hotspot), and the
  NET-INF/CSR-SLA disagreement scenario, confirming the same results at the
  HTTP layer.
- Manual grep across the full codebase for every new action-field name
  (`escalationTarget`, `csrSla*`, `customerDecision`, `customerAction`,
  `his*`, `netInf*`) before adding it, confirming none were already in use
  elsewhere.
- Manual rule-by-rule diff of all 20 NET-INF source rules against all 18
  CSR-SLA rules (condition tree, decision, action, escalationTarget) before
  deciding what to skip -- documented in the "Pack 5" section above, not
  just asserted.
