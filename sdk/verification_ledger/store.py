"""Core write operations for the verification store."""

import json
from datetime import datetime, timezone
from typing import Any, Optional

import psycopg2
import psycopg2.extras

_VALID_STATUSES = frozenset({"PENDING", "RUNNING", "SUCCESS", "FAILED", "BLOCKED", "SKIPPED"})
_VALID_ACTOR_TYPES = frozenset({"SELF_REPORTED", "THIRD_PARTY", "SYSTEM", "HUMAN"})
_VALID_CONFIDENCE = frozenset({"EXACT", "COMPATIBLE", "BEST_EFFORT"})


def connect(dsn: str):
    """Open a psycopg2 connection from a DSN string.

    Example DSN: ``postgresql://user:pass@host:5432/dbname``
    """
    conn = psycopg2.connect(dsn)
    conn.autocommit = True
    return conn


def _validate(status, actor_type, confidence):
    if status not in _VALID_STATUSES:
        raise ValueError(f"invalid status: {status}")
    if actor_type not in _VALID_ACTOR_TYPES:
        raise ValueError(f"invalid actor_type: {actor_type}")
    if confidence is not None and confidence not in _VALID_CONFIDENCE:
        raise ValueError(f"invalid confidence: {confidence}")


def record_step(
    conn,
    *,
    trace_id: str,
    step: str,
    actor: str,
    actor_type: str,
    status: str,
    evidence: Optional[dict[str, Any]] = None,
    confidence: Optional[str] = None,
    error: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> int:
    """Write one verification record. Returns the record id."""
    _validate(status, actor_type, confidence)
    sql = """
        INSERT INTO verification_store
            (trace_id, step_name, actor, actor_type, status,
             evidence, confidence, error, metadata)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """
    with conn.cursor() as cur:
        cur.execute(sql, (
            trace_id,
            step,
            actor,
            actor_type,
            status,
            psycopg2.extras.Json(evidence or {}),
            confidence,
            error,
            psycopg2.extras.Json(metadata or {}),
        ))
        return cur.fetchone()[0]


def update_step(
    conn,
    *,
    record_id: int,
    status: str,
    evidence: Optional[dict[str, Any]] = None,
    error: Optional[str] = None,
) -> None:
    """Update an existing record's status and optionally its evidence/error.

    Useful for transitioning PENDING → RUNNING → SUCCESS/FAILED.
    """
    if status not in _VALID_STATUSES:
        raise ValueError(f"invalid status: {status}")
    parts = ["status = %s"]
    params: list[Any] = [status]
    if evidence is not None:
        parts.append("evidence = %s")
        params.append(psycopg2.extras.Json(evidence))
    if error is not None:
        parts.append("error = %s")
        params.append(error)
    params.append(record_id)
    sql = f"UPDATE verification_store SET {', '.join(parts)} WHERE id = %s"
    with conn.cursor() as cur:
        cur.execute(sql, params)
