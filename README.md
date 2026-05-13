# Witness

A lightweight verification framework for autonomous system execution.

When AI agents or automated pipelines operate black-box systems, neither the human operator nor the AI can directly observe what happened. **Witness** provides a structured data exit — a shared verification store that both humans and AI can query to understand what succeeded, what failed, and why.

```
Human ─asks─► AI ─queries─► Witness Store (PostgreSQL)
                                    ▲
              Black-box systems ────┘ (write structured step records)
```

## The Problem

Modern automation creates blind spots:

- **Humans** don't write the code — they instruct AI agents. They can't read logs to verify correctness.
- **AI agents** dispatch tasks to external systems (CI/CD, cloud infrastructure, workflow engines) but can't observe execution.
- **Black-box systems** run independently. Their internal state is opaque to both humans and AI.

Traditional logs (stdout/stderr) are unstructured, hard to query, and designed for humans reading terminals — not for AI agents answering questions.

## The Solution

Every critical step in any automated pipeline writes a **structured verification record** to a shared PostgreSQL table. AI agents query this table to answer human questions like:

- "How are things going?" → `SELECT * FROM vl_task_summary`
- "What failed?" → `SELECT * FROM vl_failed_steps`  
- "Is this result trustworthy?" → `SELECT * FROM vl_trust_report`
- "What's stuck?" → `SELECT * FROM vl_stale_tasks`

## Core Concepts

### Trace

A trace is one end-to-end task. All steps in the same task share a `trace_id`.

### Step Status

| Status | Meaning |
|---|---|
| `PENDING` | Scheduled but not started |
| `RUNNING` | In progress |
| `SUCCESS` | Completed successfully |
| `FAILED` | Completed with error |
| `BLOCKED` | Cannot proceed (missing capability, unsupported platform) |
| `SKIPPED` | Intentionally not executed |

### Actor Type (Trust Level)

Not all evidence is equally trustworthy:

| Type | Who | Trust |
|---|---|---|
| `SELF_REPORTED` | The agent that did the work reports its own result | Low |
| `THIRD_PARTY` | An independent system verified the result | High |
| `SYSTEM` | Infrastructure-level event | Medium |
| `HUMAN` | A human manually verified | Highest |

### Confidence

How precise the execution context was:

| Level | Meaning |
|---|---|
| `EXACT` | Perfect match (e.g., exact platform, exact version) |
| `COMPATIBLE` | Close match (e.g., same OS family, different minor version) |
| `BEST_EFFORT` | Loose match (e.g., same package manager, different distro) |

## Quick Start

### 1. Create the database table and views

```bash
psql -f sql/schema.sql
psql -f sql/views.sql
```

### 2. Install the SDK

```bash
pip install -e sdk/
```

### 3. Record steps from your code

```python
from verification_ledger import connect, record_step

conn = connect("postgresql://user:pass@host:5432/dbname")

# System provisions infrastructure
record_step(
    conn,
    trace_id="task-001",
    step="provision",
    actor="provisioner",
    actor_type="SYSTEM",
    status="SUCCESS",
    evidence={"instance_id": "i-abc123", "region": "us-east-1"},
    confidence="EXACT",
)

# Agent self-reports deployment
record_step(
    conn,
    trace_id="task-001",
    step="deploy",
    actor="deploy-agent",
    actor_type="SELF_REPORTED",
    status="SUCCESS",
    evidence={"version": "2.4.1"},
)

# Independent service verifies the result
record_step(
    conn,
    trace_id="task-001",
    step="healthcheck",
    actor="monitoring-service",
    actor_type="THIRD_PARTY",
    status="SUCCESS",
    evidence={"http_status": 200, "latency_ms": 45},
)
```

### 4. Query results (AI or human)

```python
from verification_ledger import task_summary, failed_steps, trust_report

# "How are all tasks doing?"
for t in task_summary(conn):
    print(f"{t['trace_id']}  {t['overall_status']}  success={t['success_count']}")

# "What failed and why?"
for f in failed_steps(conn):
    print(f"{f['trace_id']}  {f['step_name']}  error={f['error']}")

# "Is this result verified by a third party?"
for r in trust_report(conn, trace_id="task-001"):
    print(f"trust_level={r['trust_level']}")
```

Or directly with SQL:

```sql
SELECT * FROM vl_task_summary;
SELECT * FROM vl_failed_steps;
SELECT * FROM vl_trust_report;
SELECT * FROM vl_stale_tasks;
SELECT * FROM vl_daily_stats;
```

## Architecture

```
witness/
├── sql/
│   ├── schema.sql                  # Core table + indexes
│   └── views.sql                   # 7 query views for AI/human consumption
├── sdk/
│   ├── pyproject.toml              # pip install -e sdk/
│   └── verification_ledger/
│       ├── __init__.py
│       ├── store.py                # record_step(), update_step()
│       └── query.py                # task_summary(), failed_steps(), trace_timeline(), etc.
├── api/
│   └── server.py                   # Optional REST API (FastAPI)
└── examples/
    └── demo_pipeline.py            # End-to-end demo
```

### Components

**Verification Store** (`sql/`) — One PostgreSQL table. Every critical step writes a row. Seven pre-built views answer the most common questions.

**Python SDK** (`sdk/`) — Two functions to write (`record_step`, `update_step`) and seven functions to read (`task_summary`, `failed_steps`, `blocked_steps`, `stale_tasks`, `trust_report`, `trace_timeline`, `daily_stats`).

**HTTP API** (`api/`) — Optional FastAPI service for systems that can't connect to PostgreSQL directly. Exposes the same read/write operations as REST endpoints.

### Optional: HTTP API

For systems that cannot connect to the database directly:

```bash
DATABASE_URL=postgresql://user:pass@host:5432/db uvicorn api.server:app --host 0.0.0.0 --port 8100
```

Endpoints:

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/steps` | Record a step |
| `PATCH` | `/api/v1/steps/{id}` | Update a step's status |
| `GET` | `/api/v1/summary` | Task-level summary |
| `GET` | `/api/v1/traces/{id}` | Full timeline for a trace |
| `GET` | `/api/v1/failed` | Failed steps |
| `GET` | `/api/v1/blocked` | Blocked steps |
| `GET` | `/api/v1/stale` | Stale tasks |
| `GET` | `/api/v1/stats` | Daily stats |

## Pre-built Query Views

| View | Question it answers |
|---|---|
| `vl_task_summary` | How is each task doing? (step counts, overall status) |
| `vl_failed_steps` | What failed and why? |
| `vl_blocked_steps` | What can't proceed and why? |
| `vl_stale_tasks` | What's been idle too long? |
| `vl_trust_report` | Are results self-reported or independently verified? |
| `vl_recent_activity` | What happened recently? |
| `vl_daily_stats` | Daily success rates and volumes |

## Design Principles

1. **Database is the source of truth** — not agent prose, not log files, not dashboards.
2. **Structured fields over free text** — AI queries with SQL, not grep.
3. **Third-party verification > self-reporting** — distinguish who produced the evidence.
4. **Explicit failure states** — FAILED, BLOCKED, SKIPPED are all different. Never leave tasks silently stuck in PENDING.
5. **Minimal footprint** — one table, one SDK function, zero external dependencies beyond PostgreSQL.

## License

MIT
