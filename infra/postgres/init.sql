-- =============================================================================
-- CedarFix AI — PostgreSQL Schema
-- =============================================================================

CREATE TABLE IF NOT EXISTS complaints (
    id                          VARCHAR(36) PRIMARY KEY,
    created_at                  TIMESTAMP DEFAULT NOW(),
    updated_at                  TIMESTAMP DEFAULT NOW(),
    status                      VARCHAR(20) DEFAULT 'pending',

    -- Raw input
    original_text               TEXT NOT NULL,
    location_lat                FLOAT,
    location_lng                FLOAT,
    location_district           VARCHAR(100),
    image_filename              VARCHAR(255),
    user_id                     VARCHAR(100),

    -- IEP-1 results
    detected_language           VARCHAR(10),
    complaint_type              VARCHAR(50),
    complaint_type_confidence   FLOAT,
    extracted_keywords          JSONB,
    location_mentions           JSONB,
    qdrant_point_id             VARCHAR(50),

    -- IEP-4 results
    duplicate_status            VARCHAR(20) DEFAULT 'NEW',
    duplicate_of                VARCHAR(36),
    cluster_id                  VARCHAR(36),
    escalation_signal           BOOLEAN DEFAULT FALSE,

    -- IEP-5 results
    severity                    VARCHAR(10),
    priority_score              FLOAT,

    -- IEP-6 results
    assigned_entity             VARCHAR(100),
    routing_confidence          FLOAT,
    auto_routed                 BOOLEAN,
    requires_review             BOOLEAN DEFAULT FALSE,

    -- Metadata
    total_pipeline_ms           INTEGER,
    full_decision_json          JSONB
);

CREATE INDEX IF NOT EXISTS idx_complaints_created_at ON complaints(created_at);
CREATE INDEX IF NOT EXISTS idx_complaints_status ON complaints(status);
CREATE INDEX IF NOT EXISTS idx_complaints_complaint_type ON complaints(complaint_type);
CREATE INDEX IF NOT EXISTS idx_complaints_severity ON complaints(severity);
CREATE INDEX IF NOT EXISTS idx_complaints_assigned_entity ON complaints(assigned_entity);
CREATE INDEX IF NOT EXISTS idx_complaints_requires_review ON complaints(requires_review);


CREATE TABLE IF NOT EXISTS clusters (
    id                  VARCHAR(36) PRIMARY KEY,
    created_at          TIMESTAMP DEFAULT NOW(),
    updated_at          TIMESTAMP DEFAULT NOW(),
    complaint_type      VARCHAR(50),
    dominant_district   VARCHAR(100),
    member_count        INTEGER DEFAULT 0,
    trend               VARCHAR(20) DEFAULT 'stable',
    last_run_at         TIMESTAMP
);


CREATE TABLE IF NOT EXISTS admin_corrections (
    id                      SERIAL PRIMARY KEY,
    complaint_id            VARCHAR(36) NOT NULL,
    admin_id                VARCHAR(100) NOT NULL,
    correction_timestamp    TIMESTAMP DEFAULT NOW(),
    corrected_routing       VARCHAR(100),
    corrected_severity      VARCHAR(10),
    corrected_complaint_type VARCHAR(50),
    notes                   TEXT,
    applied_to_training     BOOLEAN DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_corrections_complaint_id ON admin_corrections(complaint_id);
CREATE INDEX IF NOT EXISTS idx_corrections_applied ON admin_corrections(applied_to_training);


CREATE TABLE IF NOT EXISTS human_review_queue (
    id                  SERIAL PRIMARY KEY,
    created_at          TIMESTAMP DEFAULT NOW(),
    complaint_id        VARCHAR(36),
    validation_status   VARCHAR(30) NOT NULL,   -- needs_clarification | human_review
    review_reason       TEXT NOT NULL,
    original_text       TEXT,
    image_filename      VARCHAR(255),
    image_detected_type VARCHAR(50),            -- what image showed (e.g. flooding)
    text_detected_type  VARCHAR(50),            -- what text claimed (e.g. pothole)
    resolved            BOOLEAN DEFAULT FALSE,
    resolved_at         TIMESTAMP,
    resolved_by         VARCHAR(100),
    resolution_notes    TEXT
);

CREATE INDEX IF NOT EXISTS idx_hrq_resolved    ON human_review_queue(resolved);
CREATE INDEX IF NOT EXISTS idx_hrq_created_at  ON human_review_queue(created_at);
CREATE INDEX IF NOT EXISTS idx_hrq_status      ON human_review_queue(validation_status);


CREATE TABLE IF NOT EXISTS model_performance_log (
    id              SERIAL PRIMARY KEY,
    logged_at       TIMESTAMP DEFAULT NOW(),
    model_name      VARCHAR(100) NOT NULL,
    model_version   VARCHAR(50),
    metric_name     VARCHAR(100) NOT NULL,
    metric_value    FLOAT NOT NULL,
    window_days     INTEGER DEFAULT 7
);

-- =============================================================================
-- Routing Knowledge Base
-- =============================================================================

CREATE TABLE IF NOT EXISTS routing_knowledge (
    id                  VARCHAR(36) PRIMARY KEY,
    entity_name         VARCHAR(100) NOT NULL,
    entity_enum         VARCHAR(100) NOT NULL,
    entity_type         VARCHAR(30),
    short_name          VARCHAR(20),
    governs_nat         BOOLEAN DEFAULT FALSE,
    governorates        JSONB DEFAULT '[]',
    districts           JSONB DEFAULT '[]',
    municipalities      JSONB DEFAULT '[]',
    complaint_types     JSONB DEFAULT '[]',
    keywords            JSONB DEFAULT '[]',
    not_responsible     JSONB DEFAULT '[]',
    description         TEXT,
    confidence_prior    FLOAT DEFAULT 0.85,
    hotline             VARCHAR(50),
    qdrant_point_id     VARCHAR(50),
    updated_at          TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_rk_entity_enum ON routing_knowledge(entity_enum);
CREATE INDEX IF NOT EXISTS idx_rk_entity_type ON routing_knowledge(entity_type);


-- =============================================================================
-- Lebanese Locations Lookup
-- =============================================================================

CREATE TABLE IF NOT EXISTS lb_locations (
    id              SERIAL PRIMARY KEY,
    name_en         VARCHAR(100) NOT NULL,
    name_ar         VARCHAR(100),
    aliases         JSONB DEFAULT '[]',
    municipality    VARCHAR(100),
    district        VARCHAR(100),
    governorate     VARCHAR(100),
    lat             FLOAT,
    lng             FLOAT,
    UNIQUE(name_en, municipality)
);

CREATE INDEX IF NOT EXISTS idx_loc_district    ON lb_locations(district);
CREATE INDEX IF NOT EXISTS idx_loc_governorate ON lb_locations(governorate);
CREATE INDEX IF NOT EXISTS idx_loc_name_en     ON lb_locations(name_en);


-- =============================================================================
-- User Reputation
-- =============================================================================

CREATE TABLE IF NOT EXISTS user_reputation (
    user_id             VARCHAR(100) PRIMARY KEY,
    first_seen          TIMESTAMP DEFAULT NOW(),
    total_submissions   INTEGER DEFAULT 0,
    valid_submissions   INTEGER DEFAULT 0,
    spam_count          INTEGER DEFAULT 0,
    moderation_flags    INTEGER DEFAULT 0,
    banned_until        TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_user_rep_banned ON user_reputation(banned_until);


-- =============================================================================
-- Moderation Audit Log
-- =============================================================================

CREATE TABLE IF NOT EXISTS moderation_audit (
    id              SERIAL PRIMARY KEY,
    complaint_id    VARCHAR(36),
    user_id         VARCHAR(100),
    decision        VARCHAR(20) NOT NULL,       -- PASS | FLAG | REJECT
    reason          TEXT,
    heuristic_flags JSONB DEFAULT '[]',
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_mod_audit_decision    ON moderation_audit(decision);
CREATE INDEX IF NOT EXISTS idx_mod_audit_user        ON moderation_audit(user_id);
CREATE INDEX IF NOT EXISTS idx_mod_audit_created_at  ON moderation_audit(created_at);


-- =============================================================================
-- Type Correction Accuracy — Materialized View (refreshed by monitoring service)
-- =============================================================================

CREATE MATERIALIZED VIEW IF NOT EXISTS type_correction_rates AS
SELECT
    c.complaint_type,
    COUNT(*)                                                AS total_complaints,
    COUNT(ac.id)                                            AS corrected_count,
    ROUND(
        1.0 - (COUNT(ac.id)::NUMERIC / NULLIF(COUNT(*), 0)),
        4
    )                                                       AS model_accuracy,
    MIN(c.created_at)                                       AS window_start,
    MAX(c.created_at)                                       AS window_end
FROM complaints c
LEFT JOIN admin_corrections ac
    ON c.id = ac.complaint_id
    AND ac.corrected_complaint_type IS NOT NULL
WHERE c.created_at >= NOW() - INTERVAL '30 days'
GROUP BY c.complaint_type;

CREATE UNIQUE INDEX IF NOT EXISTS idx_tcr_type ON type_correction_rates(complaint_type);

-- =============================================================================
-- Users & Authentication
-- =============================================================================

CREATE TABLE IF NOT EXISTS users (
    id              VARCHAR(36) PRIMARY KEY,
    username        VARCHAR(100) UNIQUE NOT NULL,
    password_hash   VARCHAR(255) NOT NULL,
    role            VARCHAR(20) DEFAULT 'user',   -- 'user' | 'admin'
    created_at      TIMESTAMP DEFAULT NOW(),
    last_login      TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_role     ON users(role);

