"""Read-only query helpers for AI consumers and human operators.

Each function returns a list of dicts — ready to be serialized as JSON
or printed in a table.
"""

from typing import Optional

import psycopg2.extras


def _fetchall(conn, sql, params=None):
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params or ())
        return [dict(row) for row in cur.fetchall()]


def task_summary(conn, *, trace_id: Optional[str] = None, limit: int = 50):
    """One row per trace with step counts and overall status."""
    if trace_id:
        return _fetchall(conn, "SELECT * FROM vl_task_summary WHERE trace_id = %s", (trace_id,))
    return _fetchall(conn, "SELECT * FROM vl_task_summary ORDER BY last_activity DESC LIMIT %s", (limit,))


def failed_steps(conn, *, trace_id: Optional[str] = None, limit: int = 50):
    """Steps that ended in FAILED, newest first."""
    if trace_id:
        return _fetchall(conn, "SELECT * FROM vl_failed_steps WHERE trace_id = %s ORDER BY created_at DESC", (trace_id,))
    return _fetchall(conn, "SELECT * FROM vl_failed_steps LIMIT %s", (limit,))


def blocked_steps(conn, *, trace_id: Optional[str] = None, limit: int = 50):
    """Steps that are BLOCKED (cannot proceed)."""
    if trace_id:
        return _fetchall(conn, "SELECT * FROM vl_blocked_steps WHERE trace_id = %s ORDER BY created_at DESC", (trace_id,))
    return _fetchall(conn, "SELECT * FROM vl_blocked_steps LIMIT %s", (limit,))


def stale_tasks(conn, *, hours: int = 2):
    """Traces with no activity for the given number of hours while still having pending/running steps."""
    return _fetchall(conn, """
        SELECT trace_id,
               max(created_at) AS last_activity,
               NOW() - max(created_at) AS idle_duration,
               count(*) FILTER (WHERE status = 'RUNNING') AS still_running,
               count(*) FILTER (WHERE status = 'PENDING') AS still_pending
        FROM verification_store
        GROUP BY trace_id
        HAVING max(created_at) < NOW() - make_interval(hours => %s)
           AND count(*) FILTER (WHERE status IN ('RUNNING','PENDING')) > 0
    """, (hours,))


def trust_report(conn, *, trace_id: Optional[str] = None, limit: int = 50):
    """How many successes are self-reported vs third-party verified."""
    if trace_id:
        return _fetchall(conn, "SELECT * FROM vl_trust_report WHERE trace_id = %s", (trace_id,))
    return _fetchall(conn, "SELECT * FROM vl_trust_report ORDER BY trace_id LIMIT %s", (limit,))


def trace_timeline(conn, trace_id: str):
    """Full step-by-step timeline for a single trace, oldest first."""
    return _fetchall(conn, """
        SELECT id, step_name, actor, actor_type, status, confidence, error, evidence, created_at
        FROM verification_store
        WHERE trace_id = %s
        ORDER BY created_at, id
    """, (trace_id,))


def daily_stats(conn, *, days: int = 7):
    """Aggregated stats per day for the last N days."""
    return _fetchall(conn, """
        SELECT * FROM vl_daily_stats
        WHERE day >= (CURRENT_DATE - make_interval(days => %s))
        ORDER BY day DESC
    """, (days,))
