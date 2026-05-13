# Witness

[English](README.md) | 中文

一个轻量级的自动化系统执行验证框架。

当 AI agent 或自动化流水线操作黑盒系统时，人和 AI 都无法直接观察执行过程。**Witness** 提供了一个结构化的数据出口——一个人和 AI 都能查询的共享验证存储，用来了解什么成功了、什么失败了、以及为什么。

```
人 ─提问─► AI ─查询─► Witness 存储 (PostgreSQL)
                              ▲
            黑盒系统 ─────────┘ (写入结构化的步骤记录)
```

## 解决什么问题

现代自动化产生了盲区：

- **人**不写代码——他们指导 AI agent。他们无法通过阅读日志来验证正确性。
- **AI agent** 把任务派发给外部系统（CI/CD、云基础设施、工作流引擎），但看不到执行过程。
- **黑盒系统**独立运行，内部状态对人和 AI 都是不透明的。

传统日志（stdout/stderr）是非结构化的，难以查询，是为人类读终端设计的——不是为 AI agent 回答问题设计的。

## 解决方案

自动化流水线中的每个关键步骤都向 PostgreSQL 表写入一条**结构化的验证记录**。AI agent 查询这张表来回答人的问题：

- "现在进展如何？" → `SELECT * FROM vl_task_summary`
- "什么失败了？" → `SELECT * FROM vl_failed_steps`
- "结果可信吗？" → `SELECT * FROM vl_trust_report`
- "什么卡住了？" → `SELECT * FROM vl_stale_tasks`

## 核心概念

### 追踪 (Trace)

一个 trace 代表一个端到端的任务。同一个任务的所有步骤共享一个 `trace_id`。

### 步骤状态

| 状态 | 含义 |
|---|---|
| `PENDING` | 已调度但未开始 |
| `RUNNING` | 执行中 |
| `SUCCESS` | 成功完成 |
| `FAILED` | 执行失败 |
| `BLOCKED` | 无法继续（缺少能力、不支持的平台等） |
| `SKIPPED` | 被有意跳过 |

### 行为者类型（信任等级）

不是所有证据都同等可信：

| 类型 | 谁 | 信任度 |
|---|---|---|
| `SELF_REPORTED` | 执行操作的 agent 自己报告结果 | 低 |
| `THIRD_PARTY` | 独立系统验证了结果 | 高 |
| `SYSTEM` | 基础设施层面的事件 | 中 |
| `HUMAN` | 人工手动验证 | 最高 |

### 置信度

执行上下文的精确程度：

| 等级 | 含义 |
|---|---|
| `EXACT` | 精确匹配（如精确的平台、精确的版本） |
| `COMPATIBLE` | 近似匹配（如同一 OS 家族、不同小版本） |
| `BEST_EFFORT` | 宽松匹配（如同一包管理器、不同发行版） |

## 快速开始

### 1. 创建数据库表和视图

```bash
psql -f sql/schema.sql
psql -f sql/views.sql
```

### 2. 安装 SDK

```bash
pip install -e sdk/
```

### 3. 在代码中记录步骤

```python
from verification_ledger import connect, record_step

conn = connect("postgresql://user:pass@host:5432/dbname")

# 系统创建基础设施
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

# Agent 自报部署结果
record_step(
    conn,
    trace_id="task-001",
    step="deploy",
    actor="deploy-agent",
    actor_type="SELF_REPORTED",
    status="SUCCESS",
    evidence={"version": "2.4.1"},
)

# 独立服务验证结果
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

### 4. 查询结果（AI 或人）

```python
from verification_ledger import task_summary, failed_steps, trust_report

# "所有任务怎么样了？"
for t in task_summary(conn):
    print(f"{t['trace_id']}  {t['overall_status']}  success={t['success_count']}")

# "什么失败了？为什么？"
for f in failed_steps(conn):
    print(f"{f['trace_id']}  {f['step_name']}  error={f['error']}")

# "这个结果有第三方验证吗？"
for r in trust_report(conn, trace_id="task-001"):
    print(f"trust_level={r['trust_level']}")
```

或者直接用 SQL：

```sql
SELECT * FROM vl_task_summary;
SELECT * FROM vl_failed_steps;
SELECT * FROM vl_trust_report;
SELECT * FROM vl_stale_tasks;
SELECT * FROM vl_daily_stats;
```

## 架构

```
witness/
├── sql/
│   ├── schema.sql                  # 核心表 + 索引
│   └── views.sql                   # 7 个查询视图，供 AI 和人使用
├── sdk/
│   ├── pyproject.toml              # pip install -e sdk/
│   └── verification_ledger/
│       ├── __init__.py
│       ├── store.py                # record_step(), update_step()
│       └── query.py                # task_summary(), failed_steps(), trace_timeline() 等
├── api/
│   └── server.py                   # 可选的 REST API (FastAPI)
└── examples/
    └── demo_pipeline.py            # 端到端演示
```

### 组件

**验证存储** (`sql/`) — 一张 PostgreSQL 表。每个关键步骤写一行。7 个预建视图回答最常见的问题。

**Python SDK** (`sdk/`) — 2 个写入函数（`record_step`、`update_step`）和 7 个查询函数（`task_summary`、`failed_steps`、`blocked_steps`、`stale_tasks`、`trust_report`、`trace_timeline`、`daily_stats`）。

**HTTP API** (`api/`) — 可选的 FastAPI 服务，给无法直连 PostgreSQL 的系统使用。暴露与 SDK 相同的读写接口。

### 可选：HTTP API

给无法直连数据库的系统使用：

```bash
DATABASE_URL=postgresql://user:pass@host:5432/db uvicorn api.server:app --host 0.0.0.0 --port 8100
```

接口：

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/api/v1/steps` | 记录一个步骤 |
| `PATCH` | `/api/v1/steps/{id}` | 更新步骤状态 |
| `GET` | `/api/v1/summary` | 任务级汇总 |
| `GET` | `/api/v1/traces/{id}` | 单个 trace 的完整时间线 |
| `GET` | `/api/v1/failed` | 失败的步骤 |
| `GET` | `/api/v1/blocked` | 被阻塞的步骤 |
| `GET` | `/api/v1/stale` | 停滞的任务 |
| `GET` | `/api/v1/stats` | 每日统计 |

## 预建查询视图

| 视图 | 回答什么问题 |
|---|---|
| `vl_task_summary` | 每个任务进展如何？（步骤计数、总体状态） |
| `vl_failed_steps` | 什么失败了？为什么？ |
| `vl_blocked_steps` | 什么被阻塞了？为什么？ |
| `vl_stale_tasks` | 什么停滞太久了？ |
| `vl_trust_report` | 结果是自报的还是独立验证的？ |
| `vl_recent_activity` | 最近发生了什么？ |
| `vl_daily_stats` | 每日成功率和处理量 |

## 设计原则

1. **数据库是唯一真相来源** —— 不是 agent 的文字描述，不是日志文件，不是仪表盘。
2. **结构化字段优于自由文本** —— AI 用 SQL 查询，不用 grep。
3. **第三方验证 > 自我报告** —— 区分证据的来源。
4. **显式的失败状态** —— FAILED、BLOCKED、SKIPPED 各不相同。绝不让任务悄无声息地卡在 PENDING。
5. **最小依赖** —— 一张表、一个 SDK 函数、除 PostgreSQL 外零外部依赖。

## 许可证

MIT
