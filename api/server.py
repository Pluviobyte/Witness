"""Optional HTTP API for systems that cannot connect to the database directly.

Usage:
    DATABASE_URL=postgresql://user:pass@host:5432/db uvicorn api.server:app --host 0.0.0.0 --port 8100
"""

import os
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

import psycopg2
import psycopg2.extras

app = FastAPI(title="Verification Ledger API", version="0.1.0")

DATABASE_URL = os.environ.get("DATABASE_URL", "")


def _get_conn():
    if not DATABASE_URL:
        raise HTTPException(500, "DATABASE_URL not configured")
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    return conn


class StepRecord(BaseModel):
    trace_id: str
    step: str
    actor: str
    actor_type: str = Field(pattern="^(SELF_REPORTED|THIRD_PARTY|SYSTEM|HUMAN)$")
    status: str = Field(pattern="^(PENDING|RUNNING|SUCCESS|FAILED|BLOCKED|SKIPPED)$")
    evidence: dict[str, Any] = {}
    confidence: Optional[str] = Field(None, pattern="^(EXACT|COMPATIBLE|BEST_EFFORT)$")
    error: Optional[str] = None
    metadata: dict[str, Any] = {}


class StepUpdate(BaseModel):
    status: str = Field(pattern="^(PENDING|RUNNING|SUCCESS|FAILED|BLOCKED|SKIPPED)$")
    evidence: Optional[dict[str, Any]] = None
    error: Optional[str] = None


@app.post("/api/v1/steps", status_code=201)
def create_step(body: StepRecord):
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO verification_store
                   (trace_id, step_name, actor, actor_type, status, evidence, confidence, error, metadata)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id, created_at""",
                (body.trace_id, body.step, body.actor, body.actor_type, body.status,
                 psycopg2.extras.Json(body.evidence), body.confidence, body.error,
                 psycopg2.extras.Json(body.metadata)),
            )
            row = cur.fetchone()
            return {"id": row[0], "created_at": row[1].isoformat()}
    finally:
        conn.close()


@app.patch("/api/v1/steps/{record_id}")
def update_step(record_id: int, body: StepUpdate):
    conn = _get_conn()
    try:
        parts, params = ["status = %s"], [body.status]
        if body.evidence is not None:
            parts.append("evidence = %s")
            params.append(psycopg2.extras.Json(body.evidence))
        if body.error is not None:
            parts.append("error = %s")
            params.append(body.error)
        params.append(record_id)
        with conn.cursor() as cur:
            cur.execute(f"UPDATE verification_store SET {', '.join(parts)} WHERE id = %s RETURNING id", params)
            if cur.fetchone() is None:
                raise HTTPException(404, f"record {record_id} not found")
        return {"ok": True}
    finally:
        conn.close()


def _query(conn, sql, params=None):
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params or ())
        return [dict(r) for r in cur.fetchall()]


@app.get("/api/v1/summary")
def get_summary(limit: int = 50):
    conn = _get_conn()
    try:
        return _query(conn, "SELECT * FROM vl_task_summary ORDER BY last_activity DESC LIMIT %s", (limit,))
    finally:
        conn.close()


@app.get("/api/v1/traces/{trace_id}")
def get_trace(trace_id: str):
    conn = _get_conn()
    try:
        rows = _query(conn, """
            SELECT id, step_name, actor, actor_type, status, confidence, error, evidence, created_at
            FROM verification_store WHERE trace_id = %s ORDER BY created_at, id
        """, (trace_id,))
        if not rows:
            raise HTTPException(404, f"trace {trace_id} not found")
        return {"trace_id": trace_id, "steps": rows}
    finally:
        conn.close()


@app.get("/api/v1/failed")
def get_failed(limit: int = 50):
    conn = _get_conn()
    try:
        return _query(conn, "SELECT * FROM vl_failed_steps LIMIT %s", (limit,))
    finally:
        conn.close()


@app.get("/api/v1/blocked")
def get_blocked(limit: int = 50):
    conn = _get_conn()
    try:
        return _query(conn, "SELECT * FROM vl_blocked_steps LIMIT %s", (limit,))
    finally:
        conn.close()


@app.get("/api/v1/stale")
def get_stale(hours: int = 2):
    conn = _get_conn()
    try:
        return _query(conn, """
            SELECT trace_id, max(created_at) AS last_activity,
                   NOW()-max(created_at) AS idle_duration,
                   count(*) FILTER (WHERE status='RUNNING') AS still_running,
                   count(*) FILTER (WHERE status='PENDING') AS still_pending
            FROM verification_store GROUP BY trace_id
            HAVING max(created_at) < NOW()-make_interval(hours=>%s)
               AND count(*) FILTER (WHERE status IN ('RUNNING','PENDING')) > 0
        """, (hours,))
    finally:
        conn.close()


@app.get("/api/v1/stats")
def get_daily_stats(days: int = 7):
    conn = _get_conn()
    try:
        return _query(conn, "SELECT * FROM vl_daily_stats WHERE day >= CURRENT_DATE - make_interval(days=>%s) ORDER BY day DESC", (days,))
    finally:
        conn.close()
