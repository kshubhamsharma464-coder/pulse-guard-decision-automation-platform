-- ============================================================
-- Telecom Network Incident Decision Automation Platform
-- Core schema — PostgreSQL 14+ (JSONB, GIN indexing)
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
-- Individual rules. conditions/actions are JSONB so business
-- teams can edit via an admin UI without a redeploy.
-- ------------------------------------------------------------
CREATE TABLE rules (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_set_id      UUID NOT NULL REFERENCES rule_sets(id) ON DELETE CASCADE,
    rule_code        VARCHAR(20) NOT NULL,      -- e.g. R001
    name             VARCHAR(200) NOT NULL,
    description      TEXT,
    category         VARCHAR(50) NOT NULL,
                     -- IMPACT | SLA | VIP | EMERGENCY | HISTORICAL | EXTERNAL_CONTEXT
                     -- | SUPPRESSION | CAPACITY | SECURITY | COMPETITIVE_RISK | REGULATORY
    priority_weight  INT NOT NULL CHECK (priority_weight BETWEEN 0 AND 100),
    conflict_group   VARCHAR(50),               -- rules competing for the same decision field
    is_suppressor    BOOLEAN NOT NULL DEFAULT false,
    non_suppressible BOOLEAN NOT NULL DEFAULT false, -- cannot be vetoed by any suppressor
    enabled          BOOLEAN NOT NULL DEFAULT true,
    conditions       JSONB NOT NULL,            -- JsonLogic-style expression tree
    actions          JSONB NOT NULL,            -- decision fragment to merge on match
    valid_from       TIMESTAMPTZ NOT NULL DEFAULT now(),
    valid_to         TIMESTAMPTZ,
    created_by       VARCHAR(100) NOT NULL,
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (rule_set_id, rule_code)
);

CREATE INDEX idx_rules_conditions_gin ON rules USING GIN (conditions);
CREATE INDEX idx_rules_actions_gin    ON rules USING GIN (actions);
CREATE INDEX idx_rules_active         ON rules (rule_set_id) WHERE enabled = true;

-- ------------------------------------------------------------
-- Raw + enriched incidents
-- ------------------------------------------------------------
CREATE TABLE incidents (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id      VARCHAR(50) UNIQUE NOT NULL,
    tower_id         VARCHAR(50),
    region           VARCHAR(50),
    raw_payload      JSONB NOT NULL,
    enriched_context JSONB,             -- weather, maintenance, historical, SLA lookup merged in
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
    decision               JSONB NOT NULL,   -- final merged decision object
    matched_rules          JSONB NOT NULL,   -- [{rule_code, name, weight, category}]
    rejected_rules         JSONB NOT NULL,
    suppressed_rules       JSONB NOT NULL DEFAULT '[]', -- matched but vetoed by a suppressor
    explanation            TEXT NOT NULL,
    degraded_context        BOOLEAN NOT NULL DEFAULT false, -- true if external context fell back to defaults
    evaluation_duration_ms INT,
    engine_version         VARCHAR(20),
    created_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_decisions_incident ON decisions (incident_id);

-- ------------------------------------------------------------
-- Full audit trail — every rule/rule_set/decision mutation
-- ------------------------------------------------------------
CREATE TABLE audit_log (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type  VARCHAR(50) NOT NULL,   -- rule | rule_set | decision | incident
    entity_id    UUID NOT NULL,
    action       VARCHAR(50) NOT NULL,   -- created | updated | activated | deprecated | rolled_back | validated
    actor        VARCHAR(100) NOT NULL,
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
    linked_incident_ids UUID[] NOT NULL DEFAULT '{}'
);
