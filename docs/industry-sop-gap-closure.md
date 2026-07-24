# Industry-SOP gap audit and closure

This document records an explicit audit of the rule base against standard
telecom NOC / ITIL incident-management SOPs, done before writing any new
rule -- so that what got added is what was actually missing, not a guess.

## Method

Before adding anything, the full existing rule base (the original 35-rule
pack plus all six merged packs, 142 rules and counting) was checked against
the SOP categories a real telecom NOC / ITIL incident-management practice
would be expected to cover: security incident triage, auto-remediation
before human escalation, major-incident declaration and executive
communication, regulatory outage reporting, vendor/underpinning-contract
escalation, change-freeze governance, weather/safety dispatch constraints,
and acknowledgment-SLA auto-escalation. This was done by reading
`rules-seed.json` in full (not just grepping for keywords) and cross-
referencing its `families` metadata and action-field vocabulary, then
grepping the whole codebase for each SOP concept's natural field names.

## What was already covered (and by what)

Most of these categories turned out to already be built -- in some cases
the original 35-rule pack's own `families` metadata explicitly anticipated
a category (`SAFETY_REGULATORY`'s note literally says "including security
incidents (unauthorized access, DDoS)"), or its action-field vocabulary
already declared a field that no rule had ever actually set.

| SOP category | Already covered by | Notes |
|---|---|---|
| Security incident triage (DDoS, unauthorized access, physical tampering) | R015, R032 | Route to `routeToSecurityTeam`/`routeToSecurityOperationsCenter`, `isolateNetworkSegment` |
| Auto-remediation before human escalation | R029 | Known firmware bug -> `autoRemediate`/`autoRemediateAction`, before any human dispatch |
| Major incident declaration + executive communication | R017 | Regional incident storm -> `declareMajorIncident`, `notifyExecutiveEscalation`, `mergeDuplicateIncidents` |
| Regulatory reporting (emergency-services trigger) | R008, R020 | `regulatoryReportingRequired`, `regulatoryReportingDeadlineHours` |
| Weather / capacity / security-zone dispatch feasibility | R010, R023, R037 | `delayFieldDispatch`, `pauseSLAClock`, `queueDispatchWhenCapacityAvailable`, `requireSecurityEscort` |
| Government/defense and GDPR compliance constraints | R030, R031 | `publicInternetFailoverAllowed=False`, `customerNotificationDataMinimization` |
| Acknowledgment-SLA auto-escalation *mechanism* | `EscalationPolicy`/`EscalationEvent` entities, `EscalationSweep` job, `AcknowledgeEscalationUseCase` | Built (design doc §6.7), but see gap below -- the mechanism existed with nothing to walk |

None of these were touched. Re-covering them would have violated the
standing "skip if already covered" instruction the same way a sixth
externally-pasted pack would have.

## Genuine gaps found, and what was added

Three gaps were real -- either nothing in the codebase modeled the concept
at all, or (in the vendor-escalation case) the base pack's own schema had
already declared a field for it but no rule had ever populated it:

### 1. Vendor Underpinning Contract (UPC) escalation -- `SOP-VEN-001`

`escalateVendor` was present in `rules-seed.json`'s action-field vocabulary
from the original design but grep confirmed no rule, in any of the seven
packs, ever set it. Standard vendor-management SOP: when root cause is
attributed to a vendor-supplied component under a UPC, escalate through the
vendor's contractual channel with its own response clock, rather than
routing to internal engineering alone.

```
conditions: rootCauseVendorAttributed == true AND vendorContractHasUpc == true
actions: escalateVendor=true, vendorEscalationChannel="upc_priority_queue",
         vendorResponseDeadlineMinutes=60, notifyNOC=true
family: OPERATIONAL_FEASIBILITY (existing base-pack family, order 5)
```

### 2. Change-freeze governance -- `SOP-CHG-001`

Distinct from the existing "unapproved maintenance" rules (CSR-SLA-013,
NET-INF-010), which fire on `changeApproved==false`. A change freeze is a
declared, calendar-bound blackout (e.g. holiday freeze, peak-event
blackout) during which even *normally approved* changes require additional
emergency sign-off. Nothing in the codebase modeled this distinction.

```
conditions: changeFreezeActive == true AND changeLinkedToIncident == true
            AND changeEmergencyApproved == false
actions: changeFreezeViolation=true, escalateChangeAdvisoryBoard=true,
         notifyNOC=true, priorityFloor="High"
family: TEMPORAL (existing base-pack family, order 4)
```

Uses `priorityFloor`, the existing modifier mechanism `ConflictResolver`
already handles safely for multiple contributing rules (`_MODIFIER_FIELDS`),
rather than joining the `priority` conflict_group directly -- the freeze
violation nudges the floor, it doesn't try to own the categorical decision.

### 3. Mass-outage regulatory reporting threshold -- `SOP-REG-001`

R008/R020 already trigger `regulatoryReportingRequired` for emergency-
services-line impact. Most regulators (FCC NORS-style in the US, and
comparable Ofcom/TRAI thresholds) separately require reporting for
large-scale outages measured in user-minutes of impact, regardless of
whether emergency services were involved. That broader trigger didn't
exist anywhere.

```
conditions: (affectedUsers * outageDurationMinutes) >= 900000 AND serviceImpact == true
actions: regulatoryReportingRequired=true, regulatoryReportingDeadlineHours=24,
         notifyNOC=true, priorityBumpOneLevel=true
family: SAFETY_REGULATORY (existing base-pack family, order 1)
non_suppressible: true
```

Reuses the `*` JsonLogic operator already added for the SLA pack's dynamic
threshold -- no engine change needed.

## Why these three join the base pack's own vocabulary instead of getting an isolated namespace

Every pack merged before this one (SLA, vast, CSR-SLA, HIS, NET-INF) used
an isolated field namespace (`csrSla*`, `his*`, `netInf*`) because each
represented either a different decisioning vertical or third-party
authorship with its own vocabulary that had to coexist with, not replace,
the base pack's fields. These three rules are different: they're direct
extensions of the *same* incident-triage vertical the original 35 rules
already model, filling in fields (`escalateVendor`,
`regulatoryReportingRequired`, `regulatoryReportingDeadlineHours`,
`priorityFloor`, `priorityBumpOneLevel`, `notifyNOC`) and families
(`OPERATIONAL_FEASIBILITY`, `TEMPORAL`, `SAFETY_REGULATORY`) the base
pack's own design already established. Isolating them into a new
`sopVen*`/`sopChg*`/`sopReg*` namespace would have been the wrong call --
it would have hidden a genuine extension of the core model behind an
unnecessary translation layer, and thrown away the chance for these rules
to actually participate in the primary priority decision the way R008/R029/
R017 already do.

This is safe for the same reason SLA-RULE-001/008 safely joined the base
pack's `priority` conflict_group in the very first merged pack: every
*condition* field these three rules read (`rootCauseVendorAttributed`,
`vendorContractHasUpc`, `changeFreezeActive`, `changeLinkedToIncident`,
`changeEmergencyApproved`, `outageDurationMinutes`) is new and
grep-verified unused anywhere else, so none of them can match an existing
test's incident payload, and none of them can change an existing test's
outcome.

## Escalation policy seeding -- completing an already-built but unfed pipeline

Separately from the rule base: `EscalationPolicy`, `EscalationEvent`, and
the `EscalationSweep` job already existed (built during the original
architecture-review fix list), and `schema.sql`'s `escalation_policies`
table comment even specified the intended level ladder (`ENGINEER` ->
`REGIONAL_MANAGER` -> `NATIONAL_NOC` -> `VENDOR` -> `OEM`). But no concrete
policy data was ever seeded anywhere, and there was no repository/port to
look one up by severity band -- `EscalationSweep.run()` had a working
algorithm with nothing to walk.

Added `EscalationPolicyRepository` (new interface,
`app/domain/interfaces/escalation_policy_repository.py`) and
`InMemoryEscalationPolicyRepository` (`app/infrastructure/repositories/`),
seeded with one policy per severity band using the schema's own level
vocabulary and standard NOC acknowledgment-SLA timing (tighter tiers for
higher severity):

| Band | ENGINEER | REGIONAL_MANAGER | NATIONAL_NOC | VENDOR | OEM |
|---|---|---|---|---|---|
| Critical | 5 min | 15 min | 30 min | 60 min | 120 min |
| High | 15 min | 30 min | 60 min | 120 min | -- |
| Medium | 30 min | 90 min | -- | -- | -- |
| Low | 120 min | -- | -- | -- | -- |

Wired into `dependencies.py` as `escalation_policy_repository`. This is
purely additive -- a new interface, a new implementation, one new line in
the composition root -- no existing file's behavior changed. Not yet wired
to an actual scheduler (same documented limitation as the other `jobs/`
classes), but the mechanism is now genuinely exercisable end to end rather
than structurally complete and functionally inert.

## Explicitly not built (scope discipline, not an oversight)

A Post-Incident-Review (PIR)/RCA-due-date sweep is a real, standard ITIL
SOP (major incidents require a completed RCA within N business days of
resolution) and nothing in this codebase models it. It was deliberately
**not** added here: it would be a wholly new capability, not "making the
existing downstream flow work" the way the escalation-policy seeding above
is -- EscalationSweep already existed and only needed data; a PIR sweep
doesn't exist at all yet. Flagged as real, scoped future work rather than
rushed in under a task that was about closing gaps in what's already there.

## Verification performed

- Full regression suite (`pytest tests/ -q`): 85 passed (77 prior + 5 rule
  tests + 3 escalation-policy/job tests), zero failures, zero changes to
  any pre-existing test file.
- Live smoke test through the actual FastAPI app for: the INC-101
  regression case (unaffected), the mass-outage regulatory scenario, and a
  combined vendor-escalation + change-freeze scenario -- confirming
  `regulatoryReportingRequired`, `escalateVendor`, `changeFreezeViolation`,
  and the `priorityFloor`-driven `priority: "High"` all resolve correctly
  at the HTTP layer.
- `test_escalation_policy_repository_has_real_seeded_data_for_all_bands`
  and `test_escalation_sweep_runs_end_to_end_against_seeded_critical_policy`
  prove the previously-unfed `EscalationSweep` job now produces a real
  result end to end, not just that the seed data parses.
- Manual grep, before writing any new rule, confirming `escalateVendor` was
  declared but never set to `true` anywhere in the existing rule base, and
  that all six new condition field names are unused elsewhere in the
  codebase.
