-- Verification Ledger: core schema
-- Run this once to bootstrap the verification store.

CREATE TABLE IF NOT EXISTS verification_store (
    id              bigserial       PRIMARY KEY,
    trace_id        varchar(256)    NOT NULL,
    step_name       varchar(128)    NOT NULL,
    actor           varchar(128)    NOT NULL,
    actor_type      varchar(32)     NOT NULL
                        CHECK (actor_type IN ('SELF_REPORTED','THIRD_PARTY','SYSTEM','HUMAN')),
    status          varchar(32)     NOT NULL
                        CHECK (status IN ('PENDING','RUNNING','SUCCESS','FAILED','BLOCKED','SKIPPED')),
    evidence        jsonb           DEFAULT '{}'::jsonb,
    confidence      varchar(32)
                        CHECK (confidence IS NULL OR confidence IN ('EXACT','COMPATIBLE','BEST_EFFORT')),
    error           text,
    metadata        jsonb           DEFAULT '{}'::jsonb,
    created_at      timestamptz     NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_vs_trace_id     ON verification_store (trace_id);
CREATE INDEX IF NOT EXISTS idx_vs_status       ON verification_store (status);
CREATE INDEX IF NOT EXISTS idx_vs_step_name    ON verification_store (step_name);
CREATE INDEX IF NOT EXISTS idx_vs_created_at   ON verification_store (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_vs_actor_type   ON verification_store (actor_type);
