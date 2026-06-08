-- Offline GPT-4o LLM-as-Judge evaluation table.
-- Safe to run repeatedly.

CREATE TABLE IF NOT EXISTS complaint_evaluations (
    id                  SERIAL PRIMARY KEY,
    complaint_id        VARCHAR(36) NOT NULL,
    evaluated_at        TIMESTAMP DEFAULT NOW(),
    judge_model         VARCHAR(100) NOT NULL,
    prompt_version      VARCHAR(100) NOT NULL,
    text_score          INTEGER,
    image_score         INTEGER,
    alignment_score     INTEGER,
    routing_score       INTEGER,
    explanation_score   INTEGER,
    overall_score       INTEGER,
    reasoning_json      JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_complaint_evaluations_complaint_id
    ON complaint_evaluations(complaint_id);
CREATE INDEX IF NOT EXISTS idx_complaint_evaluations_evaluated_at
    ON complaint_evaluations(evaluated_at);
CREATE INDEX IF NOT EXISTS idx_complaint_evaluations_prompt_version
    ON complaint_evaluations(prompt_version);
CREATE UNIQUE INDEX IF NOT EXISTS idx_complaint_evaluations_once_per_prompt
    ON complaint_evaluations(complaint_id, prompt_version);
