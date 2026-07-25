# TeleDecision Orchestrator — Telecom Network Incident Decision Automation Platform

Companion files: `schema.sql` (Postgres/JSONB schema, v3), `rules-seed.json` (35 seeded rules across 9 families, load directly into the `rules` table).

> **Positioning.** A runtime-configurable Decision Intelligence Platform that ingests live network events, enriches them with operational context, evaluates dynamic business policies, resolves conflicting decisions, orchestrates automated mitigation workflows, and produces fully explainable, auditable outcomes for telecom network operations. The pipeline is deliberately **Incident → Context → Risk Assessment → Decision Orchestration → Mitigation Plan → Explainability → Audit Trail**, not `Incident → Priority` — because an enterprise NOC needs to know what to *do*, not just how bad it is. Swap the rule pack and the same orchestration core applies to utilities, logistics, or banking incident response — the engine doesn't know it's telecom-specific; only the rules do.

## 1. Design principle

Rules are data, not code. Each rule is a JSONB row: a **JsonLogic-style condition tree** evaluated against the incident + enriched context, and an **action fragment** merged into the final decision if the condition is true. Business teams edit rows through an admin API; the engine reads only `rule_status = 'ACTIVE'` rows within `status = 'active'` rule sets, cached in memory with a short TTL and invalidated on publish. Nothing about a rule change requires touching the rule *evaluator* code.

Four properties make this safe to run in production:

- **Deterministic conflict resolution.** Every rule carries a `priorityWeight`, a `family`/`familyOrder`, and an optional `conflictGroup`. When rules disagree on a decision field, the engine has one documented way to pick a winner — no implicit ordering, no "last rule wins."
- **Two independent signals, not one score.** A categorical `priority` (Critical/High/Medium/Low), resolved deterministically so safety-critical rules are hard stops — and a numeric `riskScore` (additive, see §3c), used for fine-grained triage ranking *within* a priority band. Pure additive scoring is intentionally **not** used for the top-level priority: an emergency-services incident whose individual signals only sum to 40 points must still be Critical, not diluted by summation. Score ranks; category decides.
- **Suppressors, exceptions, and compliance constraints are three different mechanisms.** A **suppressor** (`isSuppressor: true`) is a full rule that fires, wins a field, and can itself be overridden if a `nonSuppressible` rule matched. An **exception** (the `exceptions` field on any rule) is a self-veto — if true, the rule never fires and is logged as rejected. A **compliance constraint** (`family: COMPLIANCE`) doesn't compete for priority at all; it runs *after* conflict resolution and narrows *how* a winning action executes (e.g. "reroute, but never outside this region").
- **Governance is a first-class column set.** Every rule carries `createdBy`, `approvedBy`, `lastReviewedAt`, and a per-rule `ruleStatus` independent of the rule set's own lifecycle.

## 2. Pipeline

```
Incident received
   │
   ▼
1. Validate payload (schema check; missing/invalid required fields → manual review queue, no auto-decision)
   │
   ▼
2. Dedupe (towerId + incidentType + 10-min bucket) — same underlying event reported by multiple monitoring systems collapses to one incident
   │
   ▼
2.5 Classify — deterministic incidentType + assetTier → incidentCategory lookup (incident_category_map table).
    Not a competing rule; a normalization step every downstream rule can rely on.
   │
   ▼
3. Context Aggregation Layer — enrich from source systems, each with its own timeout + fallback (§7):
   ────────────────────────────────────────────────────────────────────────────
   Source system              → Context fields it feeds
   ────────────────────────────────────────────────────────────────────────────
   Historical incident store  → historicalFailures, repairVisitCount90Days, warrantyExpired,
                                 towerFlapCount1Hour, sameVendorFaultAssetCount24h, correlatedFaultTypesAtSite
   Weather API                 → weatherSeverity, weatherType
   Planned maintenance system  → maintenanceWindow, maintenanceType
   Fiber / asset inventory     → assetTier, incidentType-to-asset mapping
   Customer CRM                → vipCustomersAffected, customerSegment, regulatedSectorCustomerAffected
   SLA system                  → slaTier
   Traffic analytics           → networkLoad, trafficSpikePercent, packetLossPercent
   Power grid API               → powerFailureAtSite (feeds correlation, R034)
   Security alerting            → anomalyFlag, physicalTamperingDetected, unauthorizedAccessDetected
   Regional policy store        → isPeakHoursLocal, isOffHoursOrHoliday, highRiskZone, gdprScopeRegion, customerSegment
   Vendor knowledge base         → knownFirmwareBugMatch, remoteFixAvailable
   Dispatch/workforce system     → engineerCapacityAvailable
   Incident correlation state    → activeParentIncidentOnSameAsset, upstreamDependencyAlreadyResolved,
                                    duplicateOfExistingMajorIncident, regionIncidentCount10Min/7Days
   Social listening              → negativeSocialMentionSpike
   Competitive intelligence      → competitorCampaignActiveInRegion
   ────────────────────────────────────────────────────────────────────────────
   │
   ▼
4. Load active rule set for (region, tenant) — cached, GIN-indexed JSONB lookup; pin `rule_set_version_used` on the decision (§9, edge case 26)
   │
   ▼
5. Evaluate every enabled, ACTIVE-status, non-COMPLIANCE rule in family order (§3a): exceptions self-veto check, then conditions
   │
   ▼
6. Resolve conflicts per decision field → categorical `priority` + boolean/enum action fields (§3b)
   │
   ▼
6.5 Compliance constraint pass — apply COMPLIANCE-family rules against the resolved decision; they can only narrow or annotate fields (e.g. restrict reroute scope, restrict notification channel), never raise/lower priority (§6.5)
   │
   ▼
6.6 Risk score aggregation — sum `contributionScore` across matched (non-suppressed, non-self-vetoed) rules, band it (§3c)
   │
   ▼
7. Merge into final decision + mitigations objects; generate the ordered Execution Plan (§3d)
   │
   ▼
8. Build matched/rejected/suppressed trace + explanation text
   │
   ▼
8.5 Persist decision + audit log; emit async notifications (dispatch, NOC, customer, PR, retention, regulatory, vendor, SOC)
   │
   ▼
9. Optional: manual operator override (§6.6a) — always additive to the record, never destructive
   │
   ▼
10. Escalation chain runs against elapsed acknowledgment time, independent of the original evaluation (§6.7)
```

## 3a. Layered evaluation order (rule families)

Rules are grouped into families, evaluated in this fixed order. Two of the nine "families" listed aren't part of the competing-rule loop at all — `CLASSIFICATION` is a lookup table (step 2.5) and `COMPLIANCE` is a post-resolution constraint pass (step 6.5) — they're listed here for completeness because they still live in the same governance model (versioned, JSONB, auditable).

| # | Family | What it decides | Example rules |
|---|---|---|---|
| 0 | `CLASSIFICATION` | Normalizes raw `incidentType`+`assetTier` into `incidentCategory`. Lookup, not a rule contest. | `incident_category_map` table |
| 1 | `SAFETY_REGULATORY` | Hard-stop conditions — including security incidents — that always win priority and are never suppressible. | R008, R020, R015, R032 |
| 2 | `NETWORK_IMPACT` | Scale/scope of the technical outage, including asset-tier blast radius. | R001, R028, R014, R012, R002, R003 |
| 3 | `CUSTOMER_VALUE` | SLA tier, VIP, regulated/critical-sector customers. | R007, R025, R004, R005, R006 |
| 4 | `TEMPORAL` | Time-of-day/week/year acceleration or relaxation. | R013, R024 |
| 5 | `OPERATIONAL_FEASIBILITY` | Whether it's safe/practical/cost-effective to act right now. | R033, R023, R029, R010, R037 |
| 6 | `REPETITION_ESCALATION` | Chronic assets, flapping, vendor-side recurrence, hardware lifecycle. | R018, R027, R009, R036 |
| 7 | `SUPPRESSION` | Maintenance, duplicates, storms, already-active parents, cross-incident correlation. | R017, R011, R034, R026, R022 |
| 8 | `COMPETITIVE_RESILIENCE` | Churn/brand risk layered on top of the technical decision. | R016, R021 |
| 9 | `COMPLIANCE` | Post-resolution constraints — never competes, only narrows. | R030, R031 |

`familyOrder` is the primary sort key for evaluation and for tiebreaking (§3b); `priorityWeight` operates *within* that order.

## 3b. Conflict resolution algorithm

1. Run every enabled, `ACTIVE`-status, non-`COMPLIANCE` rule in `familyOrder` sequence. For each rule, check `exceptions` first — if true, reject outright (`rule_self_vetoed`). Otherwise check `conditions`; false or a missing referenced field both count as not-matched (`rule_not_matched` / `rule_skipped_missing_field`).
2. Group surviving `matched` rules by the decision field they write to.
3. **Suppressor pass**: for any field written by a rule with `isSuppressor = true`, check whether any matched rule on the same field has `nonSuppressible = true`. If yes, the suppressor is overridden (logged as *attempted-but-overridden* in `suppressed_rules`). If no, the suppressor wins and every other matched rule's value for that field is logged into `suppressed_rules`.
4. **Conflict-group pass**: where multiple matched rules disagree on a field and share a `conflictGroup`, resolve in order — (a) highest `priorityWeight`; (b) on a tie, more specific `conditions` tree (more leaf comparisons) wins; (c) on a further tie, more recent `lastReviewedAt` wins; (d) final deterministic fallback is lower `rule_code` ascending, logged as a warning. `conflictsWith` is not itself part of resolution — it's a statically-validated declaration checked at publish time (§8) so authors can't quietly introduce a new contradiction.
5. **Field merge strategy** for independent fields: booleans **OR**; `priority` takes max severity among survivors, then applies `priorityFloor` (raise-to-at-least) and `priorityBumpOneLevel` (one band up) as post-processing, in that order; `targetSLA`/`slaTarget` takes the most stringent (shortest) duration; `mitigations` merges independently of `actions` via the same OR rule; routing fields take the first non-null by descending `priorityWeight`.
6. **Named policy mapping.** For teams used to thinking in terms of discrete conflict-resolution *policies* rather than a single algorithm, here's how each maps onto the mechanism above — this table exists so an architecture reviewer can check "do you support X" without reading the algorithm line by line:

| Named policy | How it's implemented here |
|---|---|
| Highest priority wins | `conflictGroup` + `priorityWeight`, step 4(a). |
| Highest score wins | Not used for `priority` (see dual-signal rationale, §1) — but used exactly this way for `riskScore` triage ranking, §3c. |
| Merge actions | Default behavior for any field with no `conflictGroup` — independent mitigations all execute, step 5. |
| First match | Not the default (weight-based is), but achievable by setting all competing rules to equal `priorityWeight` and relying on the `rule_code`-ascending tiebreak, step 4(d). |
| Last match | Not supported by design — nondeterministic across rule-set edits and impossible to audit convincingly; use explicit `priorityWeight` instead. |
| Most specific rule | Step 4(b), the specificity tiebreak. |
| Regulatory override | `nonSuppressible: true` (step 3) for priority-contending rules; the `COMPLIANCE` family constraint pass (§6.5) for execution-shaping rules. |
| Manual override | §6.6a — a fully separate, audited layer; the automated decision is never overwritten, only superseded for execution. |

## 3c. Risk score (secondary numeric signal)

Every matched, surviving (non-suppressed, non-self-vetoed) rule with a non-null `contributionScore` adds that value to a running total (values can be negative — e.g. R011 maintenance window is `-20`, R024 off-hours is `-5`, reflecting genuinely lower operational risk). The total is clamped to `[0, 120]` and banded:

| Score range | Band |
|---|---|
| 0–30 | LOW |
| 31–50 | MEDIUM |
| 51–75 | HIGH |
| 76+ | CRITICAL |

`riskScore` is stored on the decision alongside — not instead of — the categorical `priority`. Its job is triage ordering across a queue of same-priority incidents (which of these five Critical incidents gets looked at first), and as a dashboard/analytics signal. It is explicitly **not** the mechanism that decides `priority` itself, for the reason in §1: safety and compliance rules must be deterministic hard-stops, not one input diluted into a sum.

## 3d. Execution plan generator

The merged `actions`/`mitigations` object tells you *what* should happen; the execution plan tells you *in what order*, which matters once retry/fallback semantics exist (e.g. try a remote fix before dispatching an engineer). Generation algorithm:

1. Start from a fixed base precedence: `autoRemediate` (system-executed, no wait) → `COMPLIANCE` constraints applied as annotations → `rerouteTraffic` → remote diagnostics/restart → `dispatchEngineer` → `customerNotification` → escalation triggers.
2. For any matched rule carrying a `sequencing` hint (e.g. R033: `{"tryFirst":"remoteRestart","fallbackTo":"dispatchEngineer","fallbackAfterMinutes":15}`), insert both steps with an explicit `dependsOn`/timeout relationship instead of letting the flat OR-merge fire them simultaneously.
3. Emit as an ordered array on the decision, e.g.:

```json
"executionPlan": [
  { "order": 1, "action": "Remote Diagnostics", "type": "remoteRestart" },
  { "order": 2, "action": "Traffic Reroute", "type": "rerouteTraffic", "constraint": "in-region-only" },
  { "order": 3, "action": "Dispatch Fiber Team", "type": "dispatchEngineer", "condition": "if remoteRestart fails within 15 minutes" },
  { "order": 4, "action": "Notify Enterprise Customers", "type": "customerNotification", "channelConstraint": "consented-channels-only" }
]
```

This is what an operations console actually consumes — a flat `dispatchEngineer: true` boolean tells a dashboard *that* something should happen; the execution plan tells it *when* and *in what order*, which is what makes this an orchestration engine rather than a classifier.

## 4. The rule base (35 seeded rules)

Full JSONB in `rules-seed.json`. Grouped by family, ordered by `priorityWeight` within each — see §3a for the family table. Highlights not already covered by the original 26-rule set:

- **R028 (core asset failure)** and **R014 (fiber cut)** together give the platform an asset-tier dimension: a Core Router or International Gateway failure is Critical on tier alone, independent of the affected-user count the monitoring system has managed to compute so far — which matters because core failures typically under-report early.
- **R032 (unauthorized access / physical tampering)** routes to the Security Operations Center rather than NOC — a genuinely different response path, not just a higher `priority` label on the same workflow.
- **R033 (cost optimization)** and **R029 (automation)** are the two rules that let the engine *not* dispatch a human: R033 tries a historically-reliable remote fix first with an automatic 15-minute fallback to dispatch; R029 restarts an interface with zero human involvement when the fault signature matches a known firmware bug, logged to `audit_log` with `actor='system'`.
- **R034 (correlation)** turns three simultaneous alerts (tower down + fiber down + power failure at one site) into one inferred root cause and one response, instead of three parallel — and mutually confusing — incident workflows.
- **R036 (warranty/repeat-repair)** is the MTTR/MTBF-flavored historical rule: it recommends capital replacement instead of yet another repair once an asset is out of warranty and has racked up three repairs in 90 days — genuinely different action from R009's "flag for review."
- **R030/R031 (compliance)** are the only rules in the base that don't compete for `priority` at all — they're always non-suppressible and always evaluated last, narrowing how the winning decision executes (no cross-region reroute for government/defense traffic; GDPR-consented channels only for customer notification).
- SLA rules (R004/R005/R006/R024) live in their own `conflictGroup` (`sla-target`) separate from the `priority` group, because a Gold customer can still generate a *Low*-impact incident — SLA target and priority are independent axes.

## 5. Explainability output (example)

Using the example payload from the brief (INC-101, 15,000 users, VIP, Gold, no maintenance), now with the richer decision object:

```
Matched Rules
--------------
✓ R001 - More than 10,000 users affected            (weight 90, +30 score, family NETWORK_IMPACT)
✓ R007 - VIP customers impacted                      (weight 85, +20 score, family CUSTOMER_VALUE)
✓ R004 - Gold SLA customer                            (weight 80, +15 score, family CUSTOMER_VALUE)

Rejected Rules
--------------
✗ R011 - Active planned maintenance window            (maintenanceWindow=false)
✗ R010 - Severe weather dispatch delay                (weatherSeverity=Moderate, not Severe)
✗ R017 - Mass outage / incident storm                 (regionIncidentCount10Min below threshold)
✗ R026 - Escalation suppression (active parent)        (activeParentIncidentOnSameAsset=false)

Final Decision
--------------
{
  "priority": "Critical",
  "riskScore": 65,
  "riskBand": "HIGH",
  "incidentCategory": "Mass Subscriber Outage",
  "dispatchEngineer": true,
  "notifyNOC": true,
  "rerouteTraffic": false,
  "targetSLA": "15 minutes",
  "customerNotification": true,
  "notifyAccountManager": true
}

Execution Plan
--------------
1. Dispatch Engineer (fiber-specialist not applicable; standard field team)
2. Notify NOC
3. Notify Account Manager
4. Customer Notification

Explanation
-----------
Critical because the incident impacts more than 10,000 users (R001), includes a Gold SLA
customer (R004, 15-minute target) and VIP customers (R007), and occurs outside any active
maintenance window (R011 did not match). Risk score 65 (HIGH band) reflects the combined
weight of impact, VIP, and SLA signals — used here only for triage ranking against other
concurrently open Critical incidents, not to determine the priority label itself.
```

## 6. Mitigation policies

Mitigation is a first-class, separately-merged output (`mitigations` field, distinct from `actions`):

| Mitigation flag | Fires from | Purpose |
|---|---|---|
| `rerouteTraffic` | R001, R008, R012, R014, R028 | Redirect traffic around backbone/aggregation failure or congestion. |
| `dispatchEngineer` | R001, R002, R007(indirect), R008, R014, R028 | Field intervention when it will reduce MTTR and conditions are safe. |
| `notifyNOC` | most rules above Medium severity | Standing operational visibility. |
| `customerNotification` | SLA/VIP/wide-area/weather-delay rules | Proactive comms when contractual or reputational stakes are high. |
| `openWarRoom` | R008, R015, R017, R028, R032 | Cross-team real-time coordination for safety-critical or mass-scale events. |
| `throttleNonCriticalWork` | R015, R017 | Free up NOC/engineering capacity during a major incident. |
| `fallbackToRemoteDiagnostics` | R010, R023, R033, R037 | Keep resolving when physical access is unsafe, unavailable, or simply not the cheaper first move. |
| `escalateVendor` | R027 | Push a recurring fault signature to the vendor account team, not just the local site team. |
| `autoRemediate` / `autoRemediateAction` | R029 | Zero-human-touch remediation for known, low-risk fault signatures. |
| `requireSecurityEscort` | R037 | Physical safety constraint on field dispatch in high-risk zones. |
| `routeToSecurityOperationsCenter` | R032 | Hand off to SOC instead of standard NOC workflow. |
| `recommendHardwareReplacement` | R036 | Capital-planning signal distinct from a routine repair dispatch. |
| `correlateAsSingleRootCause` / `mergeDuplicateIncidents` | R034, R017, R022 | Collapse related alerts into one response instead of N. |

Platform-level mitigations layered on top of the rule base:

- **Circuit breaker on the notification service** — paired with R017: outbound SMS/email/dispatch calls are rate-limited during a declared Major Incident.
- **SLA-breach sweep** — a scheduled job checks open decisions against `targetSLA`; at 80% elapsed with no resolution, auto-fires `priorityBumpOneLevel` and notifies the supervisor.
- **Degraded-context / confidence flag** — any decision made with a fallback/default external-context value is marked `degraded_context = true`, and `confidence_score` is reduced proportionally to how many context sources fell back to defaults, so a reviewer can distinguish a confident Critical from a best-effort one.

## 6.5 Compliance constraint pass

`COMPLIANCE`-family rules (R030, R031) run once, after conflict resolution, against the already-resolved decision object. They are structurally identical JSONB rules (same `conditions` format) but their `actions` are constraints, not contenders: R030 doesn't set `priority`, it narrows `rerouteTraffic` to `in-region-only` and forbids public-internet failover for government/defense segments even though an upstream rule (e.g. R001) already decided rerouting should happen. R031 narrows `customerNotification` to consented channels with data minimization for GDPR-scope regions. Because they're `nonSuppressible` by convention and evaluated last, no combination of impact/suppression rules can accidentally violate a compliance constraint — the constraint pass is the last word on *how* the decision executes, never on *whether* it's Critical.

## 6.6 Manual operator override

The platform never lets a human override silently overwrite the automated record. A `manual_overrides` row references the original `decisions.id`, snapshots the `original_decision`, and records the operator's `override_decision` plus a mandatory `reason`. Downstream systems execute the override, but the audit trail always shows both what the engine recommended and what actually happened — this is the difference between "the engine was wrong" and "the engine was right but an operator had situational information it didn't."

## 6.7 Escalation chain

Escalation is time-based (elapsed acknowledgment silence), not a condition on the original incident payload, so it's modeled as a policy + event log rather than a JsonLogic rule: `escalation_policies` defines an ordered chain per `severity_band` (e.g. Critical: Engineer 5min → Regional Manager 15min → National NOC 30min → Vendor 60min → OEM 120min), and a scheduled sweep writes `escalation_events` rows as each threshold is crossed without an `acknowledged_at` timestamp.

## 7. Mitigation policies for engine failure modes

- **External context source down** (weather/maintenance/SLA/vendor-history/CRM/asset-inventory API timeout). Fall back to a conservative default per source and set `decision.degraded_context = true`, reducing `confidence_score`. Never block the decision on an enrichment timeout.
- **Rule set is corrupt or has zero enabled rules.** Reject activation at publish time (§8); at evaluation time, fall back to the global default rule set, then halt and alert if that's also missing — never silently return an empty decision.
- **Incident storm overload.** R017 handles the decision layer; the notification circuit breaker (§6) handles delivery.
- **Bad rule change reaches production.** `draft → validated → shadow → active`, diffed in shadow mode before promotion, single-write rollback via `parent_version_id`.
- **Rule update arrives mid-evaluation.** An in-flight evaluation always finishes against the `rule_set_version_used` it started with (pinned on the decision record); the next incident picks up the newly active version. This avoids a single incident being evaluated against a half-old, half-new rule set.
- **Context changes after the incident was created** (e.g., a maintenance window starts five minutes after an incident was raised, or an engineer becomes available). The engine doesn't silently re-decide; it re-evaluates automatically on a defined trigger set (context-relevant field change, or the SLA-breach sweep) and produces a **new** decision record linked to the same incident, never mutates the original — the explanation for the new decision cites what changed.
- **Concurrent edits by two business users.** Optimistic concurrency on `rule_sets.version`.
- **Data staleness in enrichment.** TTL cache with a staleness flag rather than treating stale data as absent.

## 8. Runtime rule management (no restart, no redeploy)

1. Business user edits a rule's `conditions`/`actions`/`mitigations`/`sequencing` JSONB via an admin API/UI.
2. Save creates a new `rule_sets` row (`status='draft'`).
3. **Validation**: JSON Schema check; JsonLogic dry-run against historical incidents; static contradiction check cross-referencing `conflictsWith` against the live rule set. Failures block promotion past `draft`.
4. **Shadow mode**: `status='shadow'` runs in parallel on live traffic, diffed against the active set.
5. **Activate**: on sign-off (`approvedBy` recorded), flip `status='active'`, bump the in-memory cache generation — every instance picks it up on next TTL expiry, no restart.
6. **Per-rule staging.** `rule_status` (DRAFT/ACTIVE/DEPRECATED) lives on the individual rule, so one new/edited rule can be reviewed independently of the other 34.
7. **Audit**: every transition writes an `audit_log` row. Rollback is `activate` on the prior version via `parent_version_id`.

## 9. Edge cases the design accounts for

1. Missing/null required fields → blocked at validation, routed to manual review.
2. Two matched rules disagree on the same field → `conflictGroup` + `priorityWeight` → specificity → recency → `rule_code` tiebreak.
3. A rule references a field absent from the payload/context → evaluates false, logged as `rule_skipped_missing_field`.
4. Zero enabled rules in the active set → blocked, falls back to global default, then alerts.
5. Circular/contradictory rule pair → caught by `conflictsWith` static validation at publish time.
6. Incident storm (mass simultaneous outages) → R017.
7. Flapping tower → R018.
8. VIP incident during a maintenance window → resolved by `nonSuppressible`, decided per rule.
9. Multi-region incidents → `region` evaluated as an array with an `any`-style condition.
10. Multi-tenant → `rule_sets.tenant_id` and narrower `rules.tenant_id`.
11. Rollback after a bad rule deploy → single write via `parent_version_id`.
12. Bulk/batch evaluation → async queue, idempotent per `incident_id`.
13. Region overlapping an active competitor promotion → R016.
14. Timezone handling for peak/off-hours rules → incident's regional local time, never server time.
15. External context source stale or unreachable → served from cache with a staleness flag.
16. Simultaneous edits by two rule authors → optimistic concurrency, second writer rebases.
17. Malformed JSONB condition tree → schema + dry-run validation blocks promotion.
18. Unauthenticated/unauthorized rule change → RBAC (future), audited, deny-by-default.
19. SLA clock ticking during a legitimate field-safety delay → R010 explicitly pauses it.
20. Duplicate incident reports from multiple monitoring systems → deduped before rule evaluation.
21. Partial outage (only one service class affected) → `serviceClassesAffected` array scopes impact rules to the affected class's user count, not the tower's total subscriber base.
22. Conflicting context (severe weather flagged, no operational impact yet) → R010 only suppresses dispatch, never raises priority alone, so "severe weather, no incident" correctly produces no decision.
23. Monitoring noise (metric spike, no real service loss) → R015 requires *both* the spike threshold *and* an explicit `anomalyFlag`; a spike alone is informational, not incident-worthy.
24. Lower-severity incident affecting a regulated customer → R025's severity floor, independent of `affectedUsers`.
25. Escalation suppression when a higher-priority incident is already active on the same asset → R026 links as child; R022 covers the related upstream-already-resolved case.
26. **Rule set updated while an evaluation is mid-flight** → the in-flight evaluation finishes against its pinned `rule_set_version_used`; only subsequent incidents see the new version (§7).
27. **Context changes after incident creation** (maintenance starts late, engineer capacity frees up) → triggers a fresh, linked decision rather than mutating history (§7).
28. **Partial context available** → `confidence_score` is computed from the fraction of context sources that returned live (non-fallback) data, so a decision made with 3 of 12 sources degraded is visibly less confident than one made with full context, without blocking either.
29. **Invalid rule deployment** → rejected at validation (§8); last valid rule set stays active; validation errors returned to the author.
30. **Cross-region backbone failure** → regional `COMPLIANCE`/policy rules still apply per-region while R017-style storm logic can additionally declare a single, region-spanning Major Incident.
31. **Manual operator override** → §6.6, always additive, never destructive to the automated record.
32. **Autonomous auto-remediation action fails or is inconclusive** (R029) → logged to `audit_log` with `actor='system'`, and the incident is re-evaluated as if the auto-remediation hadn't happened if packet loss doesn't recover within a defined window — it doesn't silently mark the incident resolved.

## 10. Extensibility hooks already in the schema

- **Rule versioning** — `rule_sets.version` + `parent_version_id`, plus per-rule `ruleStatus`/`lastReviewedAt`/`approvedBy`.
- **Bulk evaluation** — incidents table + async queue, decisions keyed by `incident_id`, safe to batch.
- **Multi-region / multi-tenant policies** — `rule_sets.region`/`.tenant_id` with narrower per-rule overrides, global fallback.
- **Auth/RBAC** — `audit_log.actor` and `rules.approved_by` already required on every write.
- **AI-assisted rule recommendations** — structured JsonLogic conditions mean a model can propose a rule as JSON and run it through the same `draft → shadow` pipeline as a human-authored one; `conflictsWith` gives it a machine-checkable self-declaration.
- **AI-assisted root cause probability** — `decisions.root_cause_probability` is reserved in the schema (`{"Fiber Cut":0.82,...}`) as an extension point. It is deliberately **not implemented as a hard requirement here**: a defensible non-ML fallback is to derive it heuristically from the relative `contributionScore` share of matched classification-adjacent rules (e.g. R014 fiber-cut match vs R028 asset-tier match vs weather-correlated causes), while leaving room to swap in a trained model later without changing the schema.
- **Event-driven notifications** — `decision`/`actions` (what), `mitigations` (how to respond operationally), and notify*/escalate* flags (who) are separated; wire each to a topic/queue.
- **Analytics dashboards** — `matched_rules`/`rejected_rules`/`suppressed_rules`/`risk_score`/`incident_category` are all queryable JSONB/columns — "which rule fires most," "which family drives Critical decisions," "average risk score by region" are straight SQL/GIN-index queries.
- **Cross-vertical reuse** — nothing in the schema or evaluator references telecom concepts by name; `assetTier`, `incidentType`, and every context field are just JSONB keys. A utilities or logistics deployment swaps the rule pack and context sources, not the platform.

## 11. Gap review — round 1 (against the expanded rule-field/family/mitigation proposal)

Incorporated: per-rule `severityBand`, `cooldownMinutes`, `exceptions` (self-veto, distinct from suppression), explicit `conflictsWith` validated at publish, a separate `mitigations` object merged independently of `actions`, a dedicated `slaTarget` column, per-rule `region`/`tenantId` overrides, per-rule `status`/`approvedBy`/`lastReviewedAt` governance, the eight-family layered evaluation order, `openWarRoom`/`throttleNonCriticalWork`/`fallbackToRemoteDiagnostics`/`escalateVendor` as mitigation flags, and rules R022–R027 (upstream-dependency-resolved, engineer-capacity, off-hours/holiday, regulated-sector-floor, active-parent-escalation-suppression, vendor/firmware-recurrence).

## 12. Gap review — round 2 (against the Decision Orchestration Engine proposal)

Cross-checked against the fuller architecture (Context Aggregation Layer, 20 rule domains, additive scoring, execution plan generator, named conflict policies, correlation, escalation chain, compliance, manual override, richer edge-case table). Incorporated this round: the explicit Context Aggregation Layer source table (§2); a deterministic `CLASSIFICATION` stage as a lookup table rather than a competing rule (avoids polluting the priority contest with categorization); the dual-signal design — categorical `priority` plus additive `riskScore` with banding (§3c) — deliberately keeping score as a *secondary* ranking signal rather than the primary priority driver, with the reasoning made explicit; the Execution Plan Generator with `sequencing`/retry semantics (§3d); the named-conflict-policy mapping table (§3b) so each of the eight proposed policies has a documented answer, including two (`Last match`, pure score-as-priority) that are explicitly **not** supported, with reasoning, rather than silently ignored; a `COMPLIANCE` family evaluated as a post-resolution constraint pass, not a priority contender (§6.5); a fully audited manual-override layer (§6.6); a time-based escalation chain modeled separately from incident-attribute rules, since it fires on silence, not payload (§6.7); and nine new rules — R028 (core asset tier), R029 (automation/auto-remediation), R030/R031 (compliance: government reroute restriction, GDPR notification restriction), R032 (unauthorized access/physical tampering → SOC), R033 (cost optimization: remote-fix-first with fallback), R034 (correlation: multi-signal grid-failure inference), R036 (warranty/MTTR-driven replace-vs-repair), R037 (geographic high-risk zone → security escort).

Deliberately generalized rather than exhaustively enumerated: the ten weather sub-types (rain/storm/flood/snow/etc.) and ten geographic zone types collapse to `weatherSeverity`/`weatherType` and a `highRiskZone` boolean with one worked example each (R010, R037) plus a documented pattern for adding more — enumerating all twenty as near-duplicate rules would bloat the base without adding a new *mechanism*, whereas the context-field + example-rule pattern is directly extensible by a business user without an engine change. `rootCauseProbability` is reserved in the schema with a documented non-ML fallback (§10) rather than implemented as a full ML feature, since that's a genuinely different (model-serving) subsystem outside a rules-engine scope — flagging it honestly as an extension point rather than faking a probability output.
