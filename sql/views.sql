-- Verification Ledger: query views
-- These views are designed for AI agents and human operators to quickly
-- understand execution status without writing complex SQL.

-- Task-level summary: one row per trace
CREATE OR REPLACE VIEW vl_task_summary AS
SELECT
    trace_id,
    count(*)                                         AS total_steps,
    count(*) FILTER (WHERE status = 'SUCCESS')       AS success_count,
    count(*) FILTER (WHERE status = 'FAILED')        AS failed_count,
    count(*) FILTER (WHERE status = 'BLOCKED')       AS blocked_count,
    count(*) FILTER (WHERE status = 'RUNNING')       AS running_count,
    count(*) FILTER (WHERE status = 'PENDING')       AS pending_count,
    count(*) FILTER (WHERE status = 'SKIPPED')       AS skipped_count,
    min(created_at)                                  AS started_at,
    max(created_at)                                  AS last_activity,
    CASE
        WHEN count(*) FILTER (WHERE status = 'FAILED')  > 0 THEN 'HAS_FAILURES'
        WHEN count(*) FILTER (WHERE status = 'BLOCKED') > 0 THEN 'HAS_BLOCKS'
        WHEN count(*) FILTER (WHERE status IN ('RUNNING','PENDING')) > 0 THEN 'IN_PROGRESS'
        ELSE 'COMPLETE'
    END                                              AS overall_status
FROM verification_store
GROUP BY trace_id;


-- Failed steps: what went wrong and why
CREATE OR REPLACE VIEW vl_failed_steps AS
SELECT
    trace_id,
    step_name,
    actor,
    actor_type,
    error,
    evidence,
    confidence,
    created_at
FROM verification_store
WHERE status = 'FAILED'
ORDER BY created_at DESC;


-- Blocked steps: what cannot proceed and why
CREATE OR REPLACE VIEW vl_blocked_steps AS
SELECT
    trace_id,
    step_name,
    actor,
    error,
    evidence,
    created_at
FROM verification_store
WHERE status = 'BLOCKED'
ORDER BY created_at DESC;


-- Stale tasks: traces with no activity for over 2 hours while not terminal
CREATE OR REPLACE VIEW vl_stale_tasks AS
SELECT
    trace_id,
    max(created_at)                              AS last_activity,
    NOW() - max(created_at)                      AS idle_duration,
    count(*) FILTER (WHERE status = 'RUNNING')   AS still_running,
    count(*) FILTER (WHERE status = 'PENDING')   AS still_pending
FROM verification_store
GROUP BY trace_id
HAVING max(created_at) < NOW() - interval '2 hours'
   AND count(*) FILTER (WHERE status IN ('RUNNING','PENDING')) > 0;


-- Trust report: how many steps are self-reported vs third-party verified
CREATE OR REPLACE VIEW vl_trust_report AS
SELECT
    trace_id,
    count(*) FILTER (WHERE actor_type = 'SELF_REPORTED' AND status = 'SUCCESS')  AS self_reported_success,
    count(*) FILTER (WHERE actor_type = 'THIRD_PARTY'   AND status = 'SUCCESS')  AS third_party_verified,
    count(*) FILTER (WHERE actor_type = 'HUMAN'         AND status = 'SUCCESS')  AS human_verified,
    CASE
        WHEN count(*) FILTER (WHERE actor_type = 'THIRD_PARTY' AND status = 'SUCCESS') > 0 THEN 'VERIFIED'
        WHEN count(*) FILTER (WHERE actor_type = 'SELF_REPORTED' AND status = 'SUCCESS') > 0 THEN 'UNVERIFIED'
        ELSE 'NO_SUCCESS'
    END                                                                          AS trust_level
FROM verification_store
GROUP BY trace_id;


-- Recent activity: last 100 steps across all traces
CREATE OR REPLACE VIEW vl_recent_activity AS
SELECT
    id,
    trace_id,
    step_name,
    actor,
    actor_type,
    status,
    confidence,
    error,
    created_at
FROM verification_store
ORDER BY created_at DESC
LIMIT 100;


-- Daily stats: aggregated per day
CREATE OR REPLACE VIEW vl_daily_stats AS
SELECT
    date_trunc('day', created_at)::date              AS day,
    count(DISTINCT trace_id)                         AS traces,
    count(*)                                         AS total_steps,
    count(*) FILTER (WHERE status = 'SUCCESS')       AS success,
    count(*) FILTER (WHERE status = 'FAILED')        AS failed,
    count(*) FILTER (WHERE status = 'BLOCKED')       AS blocked,
    ROUND(
        100.0 * count(*) FILTER (WHERE status = 'SUCCESS') / NULLIF(count(*), 0),
        1
    )                                                AS success_rate_pct
FROM verification_store
GROUP BY date_trunc('day', created_at)::date
ORDER BY day DESC;
