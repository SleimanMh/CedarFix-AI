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


CREATE TABLE IF NOT EXISTS moderation_text_hashes (
    text_hash       VARCHAR(64) PRIMARY KEY,
    first_seen_at   TIMESTAMP DEFAULT NOW(),
    last_seen_at    TIMESTAMP DEFAULT NOW(),
    seen_count      INTEGER DEFAULT 1,
    last_user_id    VARCHAR(100)
);

CREATE INDEX IF NOT EXISTS idx_moderation_text_hashes_last_seen
    ON moderation_text_hashes(last_seen_at);


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
    source_ids          JSONB DEFAULT '[]',
    source_files        JSONB DEFAULT '[]',
    hitl_conditions     JSONB DEFAULT '[]',
    last_reviewed       VARCHAR(20),
    source_profile      VARCHAR(50),
    doc_type            VARCHAR(60) DEFAULT 'responsibility',
    route_mode          VARCHAR(80) DEFAULT 'routing_candidate',
    route_authority     VARCHAR(80) DEFAULT 'authoritative',
    source_reliability  VARCHAR(80) DEFAULT 'unknown',
    location_precision  VARCHAR(80),
    exact_match_terms   JSONB DEFAULT '[]',
    negative_signals    JSONB DEFAULT '[]',
    structured_fields   JSONB DEFAULT '{}',
    retrieval_weight    FLOAT DEFAULT 1.0,
    qdrant_point_id     VARCHAR(50),
    updated_at          TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_rk_entity_enum ON routing_knowledge(entity_enum);
CREATE INDEX IF NOT EXISTS idx_rk_entity_type ON routing_knowledge(entity_type);
CREATE INDEX IF NOT EXISTS idx_rk_doc_type ON routing_knowledge(doc_type);
CREATE INDEX IF NOT EXISTS idx_rk_route_mode ON routing_knowledge(route_mode);


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
-- LLM Audit Log
-- =============================================================================

CREATE TABLE IF NOT EXISTS llm_audit_logs (
    id              VARCHAR(36) PRIMARY KEY,
    created_at      TIMESTAMP DEFAULT NOW(),
    complaint_id    VARCHAR(36),
    service         VARCHAR(100) NOT NULL,
    call_type       VARCHAR(100) NOT NULL,
    provider        VARCHAR(50) NOT NULL,
    model           VARCHAR(200) NOT NULL,
    prompt_version  VARCHAR(100),
    status          VARCHAR(20) NOT NULL,
    latency_ms      INTEGER,
    request_payload JSONB,
    raw_output      TEXT,
    parsed_output   JSONB,
    error_type      VARCHAR(100),
    error_message   TEXT,
    artifact_uri    TEXT
);

CREATE INDEX IF NOT EXISTS idx_llm_audit_complaint_id ON llm_audit_logs(complaint_id);
CREATE INDEX IF NOT EXISTS idx_llm_audit_created_at   ON llm_audit_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_llm_audit_service      ON llm_audit_logs(service, call_type);
CREATE INDEX IF NOT EXISTS idx_llm_audit_provider     ON llm_audit_logs(provider, model);
CREATE INDEX IF NOT EXISTS idx_llm_audit_status       ON llm_audit_logs(status);


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
    email           VARCHAR(255),
    password_hash   VARCHAR(255) NOT NULL,
    role            VARCHAR(20) DEFAULT 'user',   -- 'user' | 'admin'
    created_at      TIMESTAMP DEFAULT NOW(),
    last_login      TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username_lower ON users(LOWER(username));
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_lower ON users(LOWER(email)) WHERE email IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_users_role     ON users(role);


-- =============================================================================
-- Retraining Store
-- Captures every processed complaint (all outputs) plus admin corrections,
-- so the data can be used for fine-tuning Qwen2.5 and improving RAG coverage.
--
-- Lifecycle:
--   1. Pipeline writes a row immediately after processing (raw outputs, no admin data yet).
--   2. Admin reviews the row (especially when rag_no_match=TRUE or hitl_flag_reason IS NOT NULL).
--   3. Admin sets admin_decision + optionally fills corrected_* columns.
--   4. When admin_decision = 'can_be_processed', usable_for_finetuning is set to TRUE
--      and the row becomes a gold-label training example for export.
--   5. Rows with admin_decision = 'cannot_be_processed'|'fake'|'unsupported' are kept
--      (usable_for_finetuning stays FALSE) for future taxonomy improvement analysis.
-- =============================================================================

CREATE TABLE IF NOT EXISTS retraining_store (
    id                          SERIAL PRIMARY KEY,
    complaint_id                VARCHAR(36) NOT NULL UNIQUE,
    created_at                  TIMESTAMP DEFAULT NOW(),

    -- Raw complaint input
    complaint_text              TEXT NOT NULL,
    image_filename              VARCHAR(255),

    -- Pipeline outputs stored at processing time (before any admin correction)
    text_classification_json    JSONB,          -- IEP-1: TextUnderstandingResult
    image_classification_json   JSONB,          -- IEP-2: ImageUnderstandingResult (NULL when no image)
    rag_routing_response        JSONB,          -- IEP-6: RoutingResult

    -- Pipeline flags
    pipeline_status             VARCHAR(50),    -- mirrors complaints.status
    rag_no_match                BOOLEAN DEFAULT FALSE,  -- RAG returned 0 candidates
    hitl_flag_reason            TEXT,           -- populated when pipeline triggered HITL

    -- Admin review fields
    admin_reviewed              BOOLEAN DEFAULT FALSE,
    admin_reviewed_at           TIMESTAMP,
    admin_reviewed_by           VARCHAR(100),

    -- Admin decision
    -- can_be_processed   → complaint is valid & CedarFix should handle it; corrected_* filled
    -- cannot_be_processed → valid complaint but outside CedarFix scope for now
    -- fake               → spam / test submission / not a real complaint
    -- unsupported        → complaint type not yet in taxonomy; keep for future expansion
    admin_decision              VARCHAR(30),
    admin_notes                 TEXT,

    -- Admin-corrected pipeline outputs (only required when admin_decision = 'can_be_processed')
    corrected_text_json         JSONB,          -- admin-corrected IEP-1 output
    corrected_image_json        JSONB,          -- admin-corrected IEP-2 output (when image present)
    corrected_rag_response      JSONB,          -- admin-corrected routing decision

    -- Export control
    usable_for_finetuning       BOOLEAN DEFAULT FALSE,   -- TRUE only after admin approves
    finetuning_exported         BOOLEAN DEFAULT FALSE    -- TRUE after included in a training export
);

CREATE INDEX IF NOT EXISTS idx_rts_complaint_id   ON retraining_store(complaint_id);
CREATE INDEX IF NOT EXISTS idx_rts_admin_reviewed ON retraining_store(admin_reviewed);
CREATE INDEX IF NOT EXISTS idx_rts_rag_no_match   ON retraining_store(rag_no_match);
CREATE INDEX IF NOT EXISTS idx_rts_usable         ON retraining_store(usable_for_finetuning);
CREATE INDEX IF NOT EXISTS idx_rts_exported       ON retraining_store(finetuning_exported);
CREATE INDEX IF NOT EXISTS idx_rts_admin_decision ON retraining_store(admin_decision);
CREATE INDEX IF NOT EXISTS idx_rts_created_at     ON retraining_store(created_at);

-- =============================================================================
-- Municipality Lookup — lean RAG routing profiles
-- One row per municipality profile.
-- Populated by scripts/seed_municipality_lookup.py.
-- Qdrant collection: municipality_lookup (768-dim, same model as routing_knowledge)
-- =============================================================================

CREATE TABLE IF NOT EXISTS municipality_lookup (
    -- Identity
    id                          VARCHAR(120) PRIMARY KEY,  -- municipality:M1
    version                     VARCHAR(20)  DEFAULT 'current',
    doc_type                    VARCHAR(60)  DEFAULT 'municipality_lookup_profile',
    municipality_id             VARCHAR(40)  NOT NULL,
    coverage_universe_id        VARCHAR(60),
    registry_id                 VARCHAR(60),               -- MUN-DGLAC-##### when matched
    record_status               VARCHAR(20)  DEFAULT 'unmatched',

    -- Names
    name_en                     VARCHAR(300),
    name_ar                     VARCHAR(300),

    -- Location
    governorate                 VARCHAR(100),
    district                    VARCHAR(100),
    pcode                       VARCHAR(20),
    latitude                    FLOAT,
    longitude                   FLOAT,

    -- Routing policy (all rows: blind_auto_submit=false, user_confirm=true)
    can_auto_route              BOOLEAN      DEFAULT FALSE,
    blind_auto_submit_allowed   BOOLEAN      DEFAULT FALSE,
    user_confirmation_required  BOOLEAN      DEFAULT TRUE,
    scope_disclosure_required   BOOLEAN      DEFAULT TRUE,
    routing_decision            VARCHAR(120),
    route_permission_tier       VARCHAR(80),

    -- Contact
    phone                       VARCHAR(200),
    email                       VARCHAR(300),
    website_or_social_url       VARCHAR(600),
    endpoint_level              VARCHAR(60),
    preferred_contact_or_endpoint VARCHAR(300),
    source_url                  VARCHAR(1000),

    -- RAG
    retrieval_text              TEXT,
    qdrant_point_id             VARCHAR(50),
    updated_at                  TIMESTAMP    DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_mun_lookup_municipality_id ON municipality_lookup(municipality_id);
CREATE INDEX IF NOT EXISTS idx_mun_lookup_registry_id     ON municipality_lookup(registry_id);
CREATE INDEX IF NOT EXISTS idx_mun_lookup_can_auto_route  ON municipality_lookup(can_auto_route);
CREATE INDEX IF NOT EXISTS idx_mun_lookup_governorate     ON municipality_lookup(governorate);
CREATE INDEX IF NOT EXISTS idx_mun_lookup_district        ON municipality_lookup(district);
CREATE INDEX IF NOT EXISTS idx_mun_lookup_record_status   ON municipality_lookup(record_status);

