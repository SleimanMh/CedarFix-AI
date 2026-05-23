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
