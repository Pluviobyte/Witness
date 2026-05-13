#!/usr/bin/env python3
"""
Demo: a simulated 4-step automated pipeline with verification ledger.

This shows how any black-box automation system can write structured records
into the verification store, and how an AI or human can query them to
understand execution status without looking at logs or dashboards.

Scenario: a fictional "deploy-and-verify" pipeline
  Step 1: provision   — create infrastructure
  Step 2: deploy      — deploy application
  Step 3: healthcheck — third-party verification
  Step 4: cleanup     — tear down if verified

Usage:
    DATABASE_URL=postgresql://user:pass@host:5432/db python examples/demo_pipeline.py
"""

import json
import os
import sys
import time
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "sdk"))

from verification_ledger import (
    connect,
    record_step,
    update_step,
    task_summary,
    failed_steps,
    trace_timeline,
    trust_report,
    daily_stats,
)


def simulate_pipeline(conn):
    trace_id = f"demo-{uuid.uuid4().hex[:8]}"
    print(f"\n{'='*60}")
    print(f"  Pipeline trace: {trace_id}")
    print(f"{'='*60}\n")

    # Step 1: Provision (system event)
    print("[1/4] Provisioning infrastructure...")
    rid1 = record_step(
        conn,
        trace_id=trace_id,
        step="provision",
        actor="infra-provisioner",
        actor_type="SYSTEM",
        status="SUCCESS",
        evidence={"instance_id": "i-demo123", "region": "us-west-2", "type": "t3.micro"},
        confidence="EXACT",
    )
    print(f"      Recorded (id={rid1}): instance i-demo123 provisioned\n")

    # Step 2: Deploy (agent self-reports)
    print("[2/4] Deploying application...")
    rid2 = record_step(
        conn,
        trace_id=trace_id,
        step="deploy",
        actor="deploy-agent",
        actor_type="SELF_REPORTED",
        status="RUNNING",
    )
    time.sleep(0.5)
    update_step(
        conn,
        record_id=rid2,
        status="SUCCESS",
        evidence={"version": "2.4.1", "commit": "abc1234", "deploy_time_sec": 12},
    )
    print(f"      Recorded (id={rid2}): v2.4.1 deployed (self-reported)\n")

    # Step 3: Healthcheck (third-party verification)
    print("[3/4] Running healthcheck (third-party)...")
    rid3 = record_step(
        conn,
        trace_id=trace_id,
        step="healthcheck",
        actor="monitoring-service",
        actor_type="THIRD_PARTY",
        status="SUCCESS",
        evidence={"endpoint": "https://app.example.com/health", "http_status": 200, "latency_ms": 45},
        confidence="EXACT",
    )
    print(f"      Recorded (id={rid3}): healthcheck passed (third-party verified)\n")

    # Step 4: Cleanup
    print("[4/4] Cleaning up...")
    rid4 = record_step(
        conn,
        trace_id=trace_id,
        step="cleanup",
        actor="infra-provisioner",
        actor_type="SYSTEM",
        status="SUCCESS",
        evidence={"instance_id": "i-demo123", "action": "terminated"},
    )
    print(f"      Recorded (id={rid4}): instance terminated\n")

    return trace_id


def simulate_failed_pipeline(conn):
    trace_id = f"demo-fail-{uuid.uuid4().hex[:8]}"
    print(f"\n{'='*60}")
    print(f"  Failed pipeline trace: {trace_id}")
    print(f"{'='*60}\n")

    print("[1/3] Provisioning...")
    record_step(
        conn, trace_id=trace_id, step="provision",
        actor="infra-provisioner", actor_type="SYSTEM", status="SUCCESS",
        evidence={"instance_id": "i-demo456"},
    )

    print("[2/3] Deploying...")
    record_step(
        conn, trace_id=trace_id, step="deploy",
        actor="deploy-agent", actor_type="SELF_REPORTED", status="FAILED",
        error="package installation failed: version 1.0.0 not found in repository",
        evidence={"package": "myapp", "requested_version": "1.0.0"},
    )

    print("[3/3] Healthcheck skipped due to deploy failure")
    record_step(
        conn, trace_id=trace_id, step="healthcheck",
        actor="monitoring-service", actor_type="THIRD_PARTY", status="SKIPPED",
        error="skipped because deploy step failed",
    )

    print()
    return trace_id


def ai_queries(conn, good_trace, bad_trace):
    """Simulate the queries an AI agent would run to report status."""
    print(f"\n{'='*60}")
    print("  AI Agent queries the verification store")
    print(f"{'='*60}\n")

    print("--- Question: How are all tasks doing? ---")
    for row in task_summary(conn, limit=10):
        print(f"  {row['trace_id']:30s}  status={row['overall_status']:15s}  "
              f"success={row['success_count']} failed={row['failed_count']} blocked={row['blocked_count']}")

    print("\n--- Question: What failed and why? ---")
    for row in failed_steps(conn, limit=5):
        print(f"  {row['trace_id']:30s}  step={row['step_name']:15s}  error={row['error']}")

    print(f"\n--- Question: Show me the timeline for {good_trace} ---")
    for row in trace_timeline(conn, good_trace):
        print(f"  {row['step_name']:15s}  {row['status']:10s}  actor={row['actor']:25s}  "
              f"type={row['actor_type']:15s}  confidence={row['confidence'] or '-'}")

    print(f"\n--- Question: Is {good_trace} verified by a third party? ---")
    for row in trust_report(conn, trace_id=good_trace):
        print(f"  self_reported={row['self_reported_success']}  "
              f"third_party={row['third_party_verified']}  "
              f"trust_level={row['trust_level']}")

    print("\n--- Question: Daily stats ---")
    for row in daily_stats(conn, days=1):
        print(f"  {row['day']}  traces={row['traces']}  "
              f"success={row['success']}  failed={row['failed']}  "
              f"rate={row['success_rate_pct']}%")


def main():
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("Set DATABASE_URL environment variable.")
        print("Example: DATABASE_URL=postgresql://user:pass@host:5432/db python examples/demo_pipeline.py")
        sys.exit(1)

    conn = connect(dsn)

    good_trace = simulate_pipeline(conn)
    bad_trace = simulate_failed_pipeline(conn)
    ai_queries(conn, good_trace, bad_trace)

    conn.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
