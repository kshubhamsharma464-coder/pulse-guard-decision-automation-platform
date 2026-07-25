# Telecom Network Incident Decision Automation Platform — Rule Base Design

Companion files: `schema.sql` (Postgres/JSONB schema), `rules-seed.json` (20 seeded rules, load directly into the `rules` table).

## 1. Design principle

Rules are data, not code. Each rule is a JSONB row: a **JsonLogic-style condition tree** evaluated against the incident + enriched context, and an **action fragment** merged into the final decision if the condition is true. Business teams edit rows through an admin API; the engine reads only `status = 'active'` rule sets, cached in memory with a short TTL and invalidated on publish. Nothing about a rule change requires touching the rule *evaluator* code, so "affectedUsers > 10000" becoming "> 8000" is a data update, not a deploy.

Two properties make this safe to run in production:

- **Deterministic conflict resolution.** Every rule carries a `priorityWeight` and optional `conflictGroup`. When rules disagree on a decision field, the engine has one documented way to pick a winner — no implicit ordering, no "last rule wins."
- **Suppressors, not deletions.** Rules like "active maintenance window" don't delete other rules' output — they run in a `dispatch-suppression` conflict group and can veto specific action fields, unless the winning rule is flagged `nonSuppressible` (emergency services, DDoS, regulatory).

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
3. Enrich context: historicalFailures, weather, maintenanceWindow, SLA lookup, regionIncidentCount10Min/7Days,
   competitorCampaignActiveInRegion, negativeSocialMentionSpike, towerFlapCount1Hour, isPeakHoursLocal
   (each source has a timeout + fallback — see §5 Mitigation Policies)
   │
   ▼
4. Load active rule set for (region, tenant) — cached, GIN-indexed JSONB lookup
   │
   ▼
5. Evaluate every enabled rule's condition tree against incident ∪ context
   │
   ▼
6. Resolve conflicts per decision field (§3)
   │
   ▼
7. Merge into final decision object + build matched/rejected/suppressed trace + explanation text
   │
   ▼
8. Persist decision + audit log; emit async notifications (dispatch, NOC, customer, PR, retention, regulatory)
```

## 3. Conflict resolution algorithm

1. Run every enabled rule. Split into `matched` (condition true) and `rejected` (condition false or field missing → treated as false, logged as `rule_skipped_missing_field`).
2. Group `matched` rules by the decision field they write to (`priority`, `targetSLA`, `dispatchEngineer`, …).
3. **Suppressor pass**: for any field written by a rule with `isSuppressor = true`, check whether any *matched* rule on the same field has `nonSuppressible = true`. If yes, the suppressor is overridden and logged into `suppressed_rules` as *attempted-but-overridden*. If no, the suppressor's value wins for that field and every other matched rule's value for that field is logged into `suppressed_rules`.
4. **Conflict-group pass**: for remaining fields where multiple matched rules disagree and share a `conflictGroup`, the rule with the highest `priorityWeight` wins. Tiebreak: lower `rule_code` (ascending, deterministic) wins, and a warning is logged — equal-weight collisions should be fixed by whoever authored the rules.
5. **Field merge strategy** for fields with no conflict group (independent, additive fields):
   - Boolean flags (`dispatchEngineer`, `notifyNOC`, `rerouteTraffic`, `customerNotification`, …): **OR** — true if any surviving matched rule requests true.
   - `priority`: take the **maximum severity** among surviving matched rules (`Critical > High > Medium > Low`); `priorityBumpOneLevel` actions apply after this step.
   - `targetSLA`: take the **most stringent (shortest)** duration among surviving matched rules.
   - Free-form routing fields (`routeToTeam`, `routeToSecurityTeam`): first non-null by descending `priorityWeight`.
6. Emit the human-readable explanation by walking `matched_rules` (winners) and `rejected_rules`/`suppressed_rules`, in the format shown in §6.

This means a single incident payload deterministically produces the same decision every time the same rule set version is active — required for audit and for reproducing a historical decision when investigating a complaint.

## 4. The rule base (20 seeded rules)

Full JSONB in `rules-seed.json`. Summary, ordered by `priorityWeight` (highest = most authoritative in a conflict):

| Code | Weight | Category | Rule | Non-suppressible |
|---|---|---|---|---|
| R008 | 100 | EMERGENCY | Emergency services network affected | Yes |
| R017 | 100 | SUPPRESSION | Mass outage / incident storm (>50 incidents/region/10min) | — |
| R020 | 98 | REGULATORY | Emergency alert broadcast dependency affected | Yes |
| R011 | 95 | SUPPRESSION | Active planned maintenance window | — |
| R015 | 90 | SECURITY | Suspected DDoS / traffic anomaly | Yes |
| R001 | 90 | IMPACT | >10,000 users affected | — |
| R007 | 85 | VIP | VIP customers impacted | — |
| R004 | 80 | SLA | Gold SLA tier (15-min target) | — |
| R014 | 75 | IMPACT | Fiber cut → specialist team, bypass SLA queueing | — |
| R012 | 70 | CAPACITY | Network load >90% → auto-reroute | — |
| R002 | 60 | IMPACT | 1,000–10,000 users affected | — |
| R018 | 60 | SUPPRESSION | Flapping tower (>5 up/down in 1h) | — |
| R009 | 55 | HISTORICAL | >3 failures in trailing 30 days (chronic) | — |
| R016 | 50 | COMPETITIVE_RISK | Repeat incidents + active competitor campaign in region | — |
| R013 | 45 | EXTERNAL_CONTEXT | Peak business hours (09:00–21:00 local) + >1,000 users | — |
| R010 | 40 | EXTERNAL_CONTEXT | Severe weather → delay dispatch, pause SLA clock | — |
| R021 | 40 | COMPETITIVE_RISK | Negative social-mention spike → PR escalation | — |
| R005 | 50 | SLA | Silver SLA tier (60-min target) | — |
| R003 | 20 | IMPACT | <1,000 users affected | — |
| R006 | 20 | SLA | Bronze/no SLA (4h target, default) | — |

Notable design choices:

- **R017 (mass outage)** is a suppressor at weight 100, not a normal rule — its job is to stop 50 individual engineer-dispatch and customer-notification actions from firing independently during a real backbone/power event, and instead collapse them into one Major Incident record with executive escalation. This is the single highest-leverage rule in the set for an NOC drowning in duplicate alerts.
- **R016 and R021 are the competitor-aware layer.** Deutsche Telekom-style NOCs don't just fix towers, they protect market share: repeated outages in a region where a rival is running an active retention campaign, or a complaint that's trending on social media, get routed to Retention/PR *in parallel* with the technical fix — before the customer churns or the story spreads, not after.
- **R009 (chronic failures)** doesn't just raise priority — it opens an infrastructure-review flag, because three unrelated priority bumps for the same tower over a month is really one root-cause maintenance problem being ignored.
- SLA rules (R004/R005/R006) live in their own `conflictGroup` (`sla-target`) separate from the `priority` group, because a Gold customer can still generate a *Low* impact incident (e.g. 50 users on a Gold-tier private line) — SLA target and priority are independent axes, not one field wearing two hats.

## 5. Mitigation policies

- **External context source down (weather/maintenance/SLA API timeout).** Fall back to a conservative default (`maintenanceWindow=false`, `weatherSeverity="Unknown"` treated as non-severe) and set `decision.degraded_context = true` on the persisted decision so downstream reviewers know the call was made with partial data. Never block the decision on an enrichment timeout — a stale-but-fast decision beats a correct-but-late one for a Critical incident.
- **Rule set is corrupt or has zero enabled rules.** Reject activation at publish time (validation step, §7); at evaluation time, if no active rule set is found for a region, fall back to the global default rule set, and if that's also missing, halt auto-decisioning for that scope and alert the platform team — never silently return an empty decision.
- **Incident storm overload.** R017 handles the decision layer; operationally, pair it with a circuit breaker on the notification service (rate-limit outbound SMS/email/dispatch calls) so 50 simultaneous "Critical" decisions don't themselves take down the notification pipeline.
- **Bad rule change reaches production.** New/edited rule sets go through `draft → validated → shadow → active`. In `shadow`, the rule set evaluates every real incident in parallel with the currently active set, and the two decisions are diffed; only after a sign-off on the diff report does it get promoted to `active`. Rollback is a single write (`parent_version_id` re-activated), not a redeploy.
- **SLA breach imminent.** A scheduled sweep checks open decisions against `targetSLA`; when 80% of the target window has elapsed with no resolution, auto-fire a `priorityBumpOneLevel` and notify the supervisor — this is a second, time-based evaluation pass, not a condition on the original payload.
- **Concurrent edits by two business users.** Optimistic concurrency on `rule_sets.version`; the second writer's publish is rejected with a conflict and must rebase.
- **Data staleness in enrichment.** Cache historicalFailures/competitor-campaign lookups with a TTL; if the context store is unreachable, serve the last cached value and flag it stale in `enriched_context`, rather than treating it as absent.

## 6. Explainability output (example)

Using the example payload from the brief (INC-101, 15,000 users, VIP, Gold, no maintenance):

```
Matched Rules
--------------
✓ R001 - More than 10,000 users affected            (weight 90, priority=Critical)
✓ R007 - VIP customers impacted                      (weight 85, priority=Critical)
✓ R004 - Gold SLA customer                            (weight 80, targetSLA=15 minutes)

Rejected Rules
--------------
✗ R011 - Active planned maintenance window            (maintenanceWindow=false)
✗ R010 - Severe weather dispatch delay                (weatherSeverity=Moderate, not Severe)
✗ R017 - Mass outage / incident storm                 (regionIncidentCount10Min below threshold)

Final Decision
--------------
{
  "priority": "Critical",
  "dispatchEngineer": true,
  "notifyNOC": true,
  "rerouteTraffic": false,
  "targetSLA": "15 minutes",
  "customerNotification": true,
  "notifyAccountManager": true
}

Explanation
-----------
Critical because the incident impacts more than 10,000 users (R001), includes a Gold SLA
customer (R004, 15-minute target) and VIP customers (R007), and occurs outside any active
maintenance window (R011 did not match).
```

## 7. Runtime rule management (no restart, no redeploy)

1. Business user edits a rule's `conditions`/`actions` JSONB via an admin API/UI.
2. Save creates a new `rule_sets` row (`status='draft'`) — the previous active version is untouched.
3. **Validation**: JSON Schema check on the condition/action shape, JsonLogic dry-run against a fixed sample of historical incidents, and a static check for direct self-contradictions within the same `conflictGroup` (e.g., two rules with identical conditions and opposite boolean actions and equal weight). Failures block promotion past `draft`.
4. **Shadow mode**: promote to `status='shadow'`; runs in parallel on live traffic, diffed against the active set, for N incidents or a fixed time window.
5. **Activate**: on sign-off, flip `status='active'`, deactivate the prior version (`deprecated`), bump the in-memory cache generation. Every service instance picks up the new rule set on its next cache TTL expiry (typically seconds) — no restart.
6. **Audit**: every transition writes an `audit_log` row with actor, diff, and timestamp. Rollback is `activate` on the prior version's row, preserved via `parent_version_id`.

## 8. Edge cases the design accounts for

1. Missing/null required fields → blocked at validation, routed to manual review, never silently auto-decided.
2. Two matched rules disagree on the same field → resolved by `conflictGroup` + `priorityWeight`, deterministic tiebreak by `rule_code`.
3. A rule references a field absent from the payload/context → condition evaluates false, logged as `rule_skipped_missing_field` (not an error).
4. Zero enabled rules in the active set → evaluation blocked, falls back to global default, then alerts — never returns an empty decision.
5. Circular/contradictory rule pair → caught by static validation at publish time, rejected before reaching `active`.
6. Incident storm (mass simultaneous outages) → R017 declares a Major Incident and suppresses duplicate individual notifications.
7. Flapping tower (rapid up/down) → R018 suppresses repeat dispatch, opens one root-cause ticket instead of N.
8. VIP incident during a maintenance window → resolved by `nonSuppressible` — VIP itself isn't flagged non-suppressible by default, but emergency/DDoS/regulatory are, so the design forces an explicit decision per rule about which suppressors it can survive.
9. Multi-region incidents (e.g., a backbone fiber run spanning regions) → `region` can be evaluated as an array; rules use an `any`-style condition across affected regions.
10. Multi-tenant future use (platform licensed to another operator or MVNO) → `rule_sets.tenant_id` scopes rule sets; missing tenant falls back to a default/global set.
11. Rollback after a bad rule deploy → single write via `parent_version_id`, no redeploy, full audit trail.
12. Bulk/batch evaluation after a mass event → async queue consumption, idempotent per `incident_id` (dedupe on primary key, safe to redeliver).
13. Region overlapping an active competitor promotion → R016 routes to Retention in parallel with the technical fix.
14. Timezone handling for peak-hour rules → evaluated in the incident's regional local time, never server time, to avoid a US-server-midnight bug flagging Delhi lunch-hour traffic as off-peak.
15. External context source stale or unreachable → served from cache with a staleness flag rather than treated as absent (§5).
16. Simultaneous edits by two rule authors → optimistic concurrency on `rule_sets.version`, second writer rebases.
17. Malformed JSONB condition tree submitted by a business user → schema + dry-run validation blocks promotion past `draft`.
18. Unauthenticated/unauthorized rule change (future auth layer) → RBAC required for any `rules`/`rule_sets` write, all writes audited with actor identity, deny-by-default.
19. SLA clock ticking during a legitimate field-safety delay (severe weather) → R010 explicitly pauses the SLA clock rather than letting the platform generate a false SLA-breach alert.
20. Duplicate incident reports for the same real-world event from multiple monitoring systems → deduped by `towerId + incidentType + time bucket` before rule evaluation even starts.

## 9. Extensibility hooks already in the schema

- **Rule versioning** — native via `rule_sets.version` + `parent_version_id`.
- **Bulk evaluation** — incidents table + async queue consumption; decisions keyed by `incident_id`, safe to batch.
- **Multi-region policies** — `rule_sets.region`, resolved with global fallback.
- **Multi-tenant** — `rule_sets.tenant_id`, same fallback pattern.
- **Auth/RBAC** — `audit_log.actor` already required on every write; add a `users`/`roles` table and gate the admin API without touching the evaluator.
- **AI-assisted rule recommendations** — because conditions are structured JsonLogic (not free-text), a model can propose a new rule as JSON, run it through the same `draft → shadow` pipeline as a human-authored one, with no special-cased "AI rule" type.
- **Event-driven notifications** — decision output already separates *what* happened (decision fields) from *who gets told* (notify* flags); wire each flag to a topic/queue rather than a direct call.
- **Analytics dashboards** — `decisions.matched_rules`/`rejected_rules` are queryable JSONB, so "which rule fires most" or "which region trends Critical" are straight SQL/GIN-index queries, no separate event pipeline needed.
