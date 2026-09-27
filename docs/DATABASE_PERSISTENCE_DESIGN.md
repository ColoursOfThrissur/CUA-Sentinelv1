# CUA-Sentinel Database Persistence Architecture & Table Ownership Design

## 1. Executive Summary & Principles

CUA-Sentinel uses a single-process, local-first SQLite persistence tier with 4 dedicated database files.
To ensure total reliability under concurrent background activity without corrupting task state:

1. **Strict Table Ownership**: Every table has a single authoritative repository/owner responsible for writes.
2. **Zero Agent Direct SQL**: Agents (`backend/agents/`) are strictly prohibited from issuing raw SQL (`conn.execute`, `executescript`, `cursor.execute`) or connecting directly to databases. Agents must interact exclusively through `AgentRuntime`, `ToolGateway`, `write_gate`, or typed repositories (`backend/db/repositories/`).
3. **Bounded Retries with Exponential Backoff**: Write transactions use `execute_write_transaction` which catches SQLite lock contention (`sqlite3.OperationalError` with `locked` or `busy`), applies exponential backoff with randomized jitter up to 5 attempts, and raises `DatabaseLockError` emitting structured error events rather than swallowing lock errors.
4. **Pre-Migration Safety Snapshots**: Before applying any migration scripts, `initialize_all_databases()` creates a timestamped backup snapshot in `data/.sentinel_backup/db_pre_migrate/`.
5. **WAL & Pragmas**: All connections enforce Write-Ahead Logging (`PRAGMA journal_mode=WAL`), `PRAGMA foreign_keys=ON`, and `PRAGMA busy_timeout = 30000` (30 seconds).

---

## 2. Table Ownership Matrix

| Database File | Table Name | Authoritative Owner | Readers | Mutability / Lifecycle | Retention Policy |
|---|---|---|---|---|---|
| `operational.sqlite` | `tasks` | `OperationalRepository` / `Scheduler` / `Queue` | UI, Watchdog, Agents (via Runtime) | Mutable state machine (`QUEUED` → `RUNNING` → `COMPLETED`/`FAILED`) | Indefinite (archived after 90 days) |
| `operational.sqlite` | `task_steps` | `OperationalRepository` / `AgentRuntime` | UI, Watchdog | Mutable step status (`PENDING` → `RUNNING` → terminal) with version stamps | Tied to Task lifecycle |
| `operational.sqlite` | `task_checkpoints` | `OperationalRepository` / `AgentRuntime` | `AgentRuntime` (resumption) | Append-only checkpoints per step | 24-hour freshness TTL |
| `operational.sqlite` | `operations` | `OperationalRepository` | UI, Scheduler | Mutable execution status | Tied to Task lifecycle |
| `operational.sqlite` | `worker_nodes` | `OperationalRepository` / `Watchdog` | System Status UI | Mutable heartbeats and boot status | Active nodes only |
| `operational.sqlite` | `result_cache` | `ResultCacheManager` | `AgentRuntime`, `ToolGateway` | Mutable cache with TTL | 30-minute background prune |
| `operational.sqlite` | `playbook_hints` | `ResultCacheManager` | `AgentRuntime` | Immutable hints with valid date ranges | Valid-until TTL |
| `operational.sqlite` | `user_portfolios` | `FinanceTools` / `FinanceViews` | Dashboard UI | Mutable portfolio holdings | User-managed |
| `operational.sqlite` | `user_links` | `LinkManager` | Links UI, Second Brain | Mutable bookmarks | User-managed |
| `audit.sqlite` | `audit_logs` | `AuditRepository` / `ToolGateway` | Governance UI, Security Audits | Strictly append-only | Indefinite immutable record |
| `audit.sqlite` | `system_events` | `AuditRepository` / `Watchdog` | System Status UI | Strictly append-only | Indefinite |
| `audit.sqlite` | `hitl_approval_events`| `AuditRepository` / `GovernanceEngine` | Governance UI | Strictly append-only lifecycle | Indefinite |
| `audit.sqlite` | `telemetry_events` | `AuditRepository` / `TelemetryDaemon` | Telemetry Dashboard | Append-only high-frequency metrics | 7-day rolling window |
| `audit.sqlite` | `eval_runs` | `AuditRepository` / `GoldenEval` | Eval Reports | Strictly append-only | Indefinite |
| `audit.sqlite` | `dependency_plans` | `DependencyPlanRepository` | Code Workspace UI, Executor | State machine (`REQUESTED` → `APPROVED` → `EXECUTED`) | Indefinite |
| `knowledge.sqlite` | `episodic_memory` | `KnowledgeRepository` / `AgentRuntime` | `AgentRuntime` | Tiered memory (`HOT` → `WARM` → `COLD`) | Hot=24h, Warm=7d, Cold=indefinite |
| `knowledge.sqlite` | `canonical_documents`| `KnowledgeRepository` | Second Brain, RAG | Upsert on content change | Indefinite |
| `knowledge.sqlite` | `research_claims` | `KnowledgeRepository` / `ResearcherAgent`| Synthesizer, Second Brain | Append-only factual claims | Indefinite |
| `knowledge.sqlite` | `digests` | `KnowledgeRepository` / `SynthesizerAgent` | Digest UI | Append-only topic summaries | Indefinite |
| `knowledge.sqlite` | `artifacts` | `KnowledgeRepository` | Code Workspace UI | Metadata pointer to disk storage | Indefinite |
| `state.sqlite` | `facts` | `WriteGate` (Finance Engine) | Finance State Views | Immutable append-only typed facts | Indefinite |
| `state.sqlite` | `entities` | `WriteGate` (Finance Engine) | Finance State Views | Upsert canonical keys | Indefinite |
| `state.sqlite` | `events` | `WriteGate` (Finance Engine) | State Audits | Strictly append-only | Indefinite |
| `state.sqlite` | `reviews` | `WriteGate` (Finance Engine) | Human Review Gate | Pending / Resolved human decisions | Indefinite |

---

## 3. Concurrency & Contention Handling

When multiple background loops (Scheduler, Watchdog, Telemetry, Cache Pruning, Research, MCP) operate concurrently:

1. **WAL Mode**: Readers never block writers, and writers never block readers.
2. **Busy Timeout**: SQLite connection level `PRAGMA busy_timeout = 30000` instructs SQLite's C core to wait up to 30 seconds for an open lock.
3. **Application Bounded Retry**:
   If contention persists past the core timeout or returns `database is locked`:
   ```python
   with execute_write_transaction(conn, operation_name="create_step", db_name="operational") as cur:
       cur.execute(...)
   ```
   Retries up to 5 attempts with exponential backoff:
   - Attempt 1: 0.05s + jitter
   - Attempt 2: 0.10s + jitter
   - Attempt 3: 0.20s + jitter
   - Attempt 4: 0.40s + jitter
   - Attempt 5: 0.80s + jitter
4. **Structured Error Emission**:
   If all retries are exhausted, `DatabaseLockError` is raised. A structured event `DB_WRITE_TRANSACTION_FAILED` is logged with database name, operation, retry count, and elapsed time. The failure degrades cleanly rather than corrupting task state or crashing the daemon.
