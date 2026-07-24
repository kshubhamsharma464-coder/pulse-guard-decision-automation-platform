-- ============================================================
-- Telecom Network Incident Decision Automation Platform
-- Core schema — PostgreSQL 14+ (JSONB, GIN indexing)
-- v3: adds risk scoring, execution plan, classification,
--     manual override, and escalation-chain support
-- ============================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto; -- for gen_random_uuid()

-- ------------------------------------------------------------
-- Rule sets: a named, versioned bundle of rules.
-- Only one version per (name, region, tenant) can be 'active'.
-- ------------------------------------------------------------
CREATE TABLE rule_sets (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name             VARCHAR(100) NOT NULL,
    version          INT NOT NULL,
    status           VARCHAR(20) NOT NULL DEFAULT 'draft',
                     -- draft | validated | shadow | active | deprecated | rolled_back
    region           VARCHAR(50),           -- NULL = global default
    tenant_id        UUID,                  -- NULL = default tenant (future multi-tenant)
    effective_from   TIMESTAMPTZ,
    effective_to     TIMESTAMPTZ,
    parent_version_id UUID REFERENCES rule_sets(id), -- for rollback lineage
    created_by       VARCHAR(100) NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    activated_at     TIMESTAMPTZ,
    UNIQUE (name, version, region, tenant_id)
);

CREATE UNIQUE INDEX ux_one_active_ruleset
    ON rule_sets (name, region, tenant_id)
    WHERE status = 'active';

-- ------------------------------------------------------------
-- Deterministic incident classification (not a competing rule —
-- a lookup table). Maps raw incidentType + assetTier combinations
-- to a normalized incidentCategory used by every downstream rule.
-- ------------------------------------------------------------
CREATE TABLE incident_category_map (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_type    VARCHAR(50) NOT NULL,   -- raw value from OSS payload
    asset_tier       VARCHAR(50),            -- NULL = matches any tier
    incident_category VARCHAR(50) NOT NULL,  -- normalized: e.g. "Fiber Backbone Failure"
    UNIQUE (incident_type, asset_tier)
);

-- ------------------------------------------------------------
-- Individual rules. conditions/actions are JSONB so business
-- teams can edit via an admin UI without a redeploy.
--
-- Field groups:
--   identity        rule_code, name, description
--   scoring          priority_weight, severity_band, contribution_score, family, family_order
--   evaluation       conditions, exceptions, conflict_group, conflicts_with,
--                     is_suppressor, non_suppressible, cooldown_minutes
--   output           actions, mitigations, sequencing, sla_target
--   scope            region (per-rule override), tenant_id (per-rule override)
--   lifecycle        rule_status, valid_from, valid_to
--   governance       created_by, approved_by, last_reviewed_at, updated_at
--
-- Two families are NOT part of the normal familyOrder competing-rule
-- loop: CLASSIFICATION is handled by incident_category_map above, and
-- COMPLIANCE rules are evaluated as a constraint pass AFTER conflict
-- resolution (they narrow *how* an action executes, not *whether*
-- it wins priority) — see design doc §6.5.
-- ------------------------------------------------------------
CREATE TABLE rules (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_set_id      UUID NOT NULL REFERENCES rule_sets(id) ON DELETE CASCADE,
    rule_code        VARCHAR(20) NOT NULL,      -- e.g. R001

    -- identity
    name             VARCHAR(200) NOT NULL,
    description      TEXT,

    -- scoring
    priority_weight    INT NOT NULL CHECK (priority_weight BETWEEN 0 AND 100), -- conflict-resolution weight
    severity_band      VARCHAR(20),             -- Critical | High | Medium | Low | NULL (modifier-only rule)
    contribution_score INT,                     -- additive points toward the secondary numeric riskScore; NULL/0 for pure constraints
    family              VARCHAR(40) NOT NULL,
                     -- SAFETY_REGULATORY | NETWORK_IMPACT | CUSTOMER_VALUE | TEMPORAL
                     -- | OPERATIONAL_FEASIBILITY | REPETITION_ESCALATION | SUPPRESSION
                     -- | COMPETITIVE_RESILIENCE | COMPLIANCE
    family_order     INT NOT NULL,              -- evaluation-layer order; see design doc §3a (COMPLIANCE sorts last, applied as constraint pass)

    -- evaluation
    conditions       JSONB NOT NULL,             -- JsonLogic-style expression tree; must be true to fire
    exceptions       JSONB,                       -- JsonLogic tree; if true, self-vetoes the rule (rejected, not just suppressed)
    conflict_group   VARCHAR(50),                -- rules competing for the same decision field
    conflicts_with   TEXT[] NOT NULL DEFAULT '{}', -- documented rule_codes this rule logically opposes (validated at publish)
    is_suppressor    BOOLEAN NOT NULL DEFAULT false,
    non_suppressible BOOLEAN NOT NULL DEFAULT false, -- cannot be vetoed by any suppressor
    cooldown_minutes INT NOT NULL DEFAULT 0,      -- min. minutes before this rule may re-fire notifications for the same asset

    -- output
    actions          JSONB NOT NULL,             -- decision fragment to merge on match
    mitigations      JSONB NOT NULL DEFAULT '{}', -- operational fallback actions, tracked separately from actions
    sequencing       JSONB,                       -- optional ordered/retry hint, e.g. {"tryFirst":"remoteRestart","fallbackTo":"dispatchEngineer","fallbackAfterMinutes":15}
    sla_target       VARCHAR(30),                -- dedicated, indexable SLA target (source of truth over actions.targetSLA)

    -- scope (narrower than rule_sets.region / .tenant_id; NULL = inherit from rule set)
    region           VARCHAR(50),
    tenant_id        UUID,

    -- lifecycle
    rule_status      VARCHAR(20) NOT NULL DEFAULT 'ACTIVE', -- DRAFT | ACTIVE | DEPRECATED (per-rule, independent of rule_set.status)
    enabled          BOOLEAN NOT NULL DEFAULT true,
    valid_from       TIMESTAMPTZ NOT NULL DEFAULT now(),
    valid_to         TIMESTAMPTZ,

    -- governance
    created_by       VARCHAR(100) NOT NULL,
    approved_by      VARCHAR(100),
    last_reviewed_at TIMESTAMPTZ,
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (rule_set_id, rule_code)
);

CREATE INDEX idx_rules_conditions_gin ON rules USING GIN (conditions);
CREATE INDEX idx_rules_actions_gin    ON rules USING GIN (actions);
CREATE INDEX idx_rules_mitigations_gin ON rules USING GIN (mitigations);
CREATE INDEX idx_rules_active         ON rules (rule_set_id) WHERE enabled = true AND rule_status = 'ACTIVE';
CREATE INDEX idx_rules_family_order   ON rules (rule_set_id, family_order, priority_weight DESC);

-- ------------------------------------------------------------
-- Raw + enriched incidents
-- ------------------------------------------------------------
CREATE TABLE incidents (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id      VARCHAR(50) UNIQUE NOT NULL,
    tower_id         VARCHAR(50),
    region           VARCHAR(50),
    raw_payload      JSONB NOT NULL,
    enriched_context JSONB,             -- weather, maintenance, historical, SLA lookup, CRM/asset/security context merged in
    incident_category VARCHAR(50),      -- resolved via incident_category_map at ingest
    dedupe_key       VARCHAR(150),      -- towerId + incidentType + 10-min bucket, for storm/flap dedupe
    received_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_incidents_dedupe ON incidents (dedupe_key, received_at);
CREATE INDEX idx_incidents_region_time ON incidents (region, received_at);

-- ------------------------------------------------------------
-- Decisions + explainability trace
-- ------------------------------------------------------------
CREATE TABLE decisions (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id            UUID NOT NULL REFERENCES incidents(id),
    rule_set_id            UUID NOT NULL REFERENCES rule_sets(id),
    decision               JSONB NOT NULL,   -- final merged decision object (actions), post-compliance-constraint
    mitigations            JSONB NOT NULL DEFAULT '{}', -- final merged mitigations object
    risk_score             INT,              -- additive secondary signal, 0-100+ (see design doc §3c)
    incident_category      VARCHAR(50),
    root_cause_probability JSONB,            -- optional: {"Fiber Cut":0.82,"Power Failure":0.11,...}; extension point, heuristic fallback documented in §9
    execution_plan         JSONB NOT NULL DEFAULT '[]', -- ordered [{order, action, dependsOn}]
    confidence_score       NUMERIC(5,2),     -- 0-100, reduced when context is degraded/partial
    matched_rules          JSONB NOT NULL,   -- [{rule_code, name, weight, family, severity_band, contribution_score}]
    rejected_rules         JSONB NOT NULL,   -- includes rules rejected by their own `exceptions` clause
    suppressed_rules       JSONB NOT NULL DEFAULT '[]', -- matched but vetoed by a suppressor
    compliance_constraints JSONB NOT NULL DEFAULT '[]', -- constraints applied by the post-resolution compliance pass
    explanation            TEXT NOT NULL,
    degraded_context       BOOLEAN NOT NULL DEFAULT false, -- true if external context fell back to defaults
    rule_set_version_used  INT,              -- pins the exact version evaluated, even if a newer version activates mid-flight
    evaluation_duration_ms INT,
    engine_version         VARCHAR(20),
    created_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_decisions_incident ON decisions (incident_id);

-- ------------------------------------------------------------
-- Manual operator override — the automated decision is always
-- preserved; the override is a separate, fully audited record.
-- ------------------------------------------------------------
CREATE TABLE manual_overrides (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    decision_id      UUID NOT NULL REFERENCES decisions(id),
    operator         VARCHAR(100) NOT NULL,
    original_decision JSONB NOT NULL,        -- snapshot of decisions.decision at override time
    override_decision JSONB NOT NULL,        -- the operator's effective decision
    reason           TEXT NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ------------------------------------------------------------
-- Escalation chain — time-based, triggered when an assigned
-- responder does not acknowledge within the rule-configured window.
-- Not a JsonLogic incident rule (it fires on elapsed time / silence,
-- not incident attributes), so it's modeled as a policy + event log.
-- ------------------------------------------------------------
CREATE TABLE escalation_policies (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_set_id      UUID NOT NULL REFERENCES rule_sets(id),
    applies_to_severity_band VARCHAR(20) NOT NULL, -- Critical | High | Medium | Low
    levels           JSONB NOT NULL             -- ordered: [{"level":"ENGINEER","timeoutMinutes":5},{"level":"REGIONAL_MANAGER","timeoutMinutes":15},{"level":"NATIONAL_NOC","timeoutMinutes":30},{"level":"VENDOR","timeoutMinutes":60},{"level":"OEM","timeoutMinutes":120}]
);

CREATE TABLE escalation_events (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    decision_id      UUID NOT NULL REFERENCES decisions(id),
    level            VARCHAR(30) NOT NULL,     -- ENGINEER | REGIONAL_MANAGER | NATIONAL_NOC | VENDOR | OEM
    triggered_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    acknowledged_at  TIMESTAMPTZ,
    acknowledged_by  VARCHAR(100)
);

CREATE INDEX idx_escalation_events_decision ON escalation_events (decision_id, triggered_at);

-- ------------------------------------------------------------
-- Full audit trail — every rule/rule_set/decision mutation,
-- including autonomous auto-remediation actions (actor = 'system')
-- ------------------------------------------------------------
CREATE TABLE audit_log (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type  VARCHAR(50) NOT NULL,   -- rule | rule_set | decision | incident | manual_override | auto_remediation
    entity_id    UUID NOT NULL,
    action       VARCHAR(50) NOT NULL,   -- created | updated | activated | deprecated | rolled_back | validated | approved | overridden | auto_executed
    actor        VARCHAR(100) NOT NULL,  -- username, or 'system' for autonomous actions
    diff         JSONB,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_audit_entity ON audit_log (entity_type, entity_id, created_at);

-- ------------------------------------------------------------
-- Major-incident / storm grouping (R017 support)
-- ------------------------------------------------------------
CREATE TABLE major_incidents (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    region           VARCHAR(50) NOT NULL,
    declared_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at      TIMESTAMPTZ,
    trigger_incident_count INT NOT NULL,
    inferred_root_cause VARCHAR(100),    -- populated by correlation rules, e.g. R034
    linked_incident_ids UUID[] NOT NULL DEFAULT '{}'
);

-- ------------------------------------------------------------
-- Parent/child incident linkage (R026 escalation suppression,
-- R034 correlation support)
-- ------------------------------------------------------------
CREATE TABLE incident_links (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    parent_incident_id UUID NOT NULL REFERENCES incidents(id),
    child_incident_id  UUID NOT NULL REFERENCES incidents(id),
    link_reason         VARCHAR(50) NOT NULL, -- same_asset_active_parent | correlated_regional_storm | duplicate_source | correlated_root_cause
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (parent_incident_id, child_incident_id)
);
