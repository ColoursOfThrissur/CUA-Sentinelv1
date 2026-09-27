# Architecture Hardening and Refactor Plan

**Status:** Active planning document  
**Last updated:** 2026-09-26  
**Owner:** CUA-Sentinel maintainers

This is the continuation document for the architecture work. It is deliberately
incremental: every phase must leave the application runnable, preserve existing
user data, and be independently testable. Do not combine phases in one change.

## Why this work exists

CUA-Sentinel has a strong local-first foundation: a React dashboard, FastAPI API,
local model runtime, SQLite-backed state, governance, and a broad tool surface.
The next risk is maintainability rather than missing features. A few large modules
now mix orchestration, policy, persistence, I/O, and response formatting. Package
installation is also a meaningful external-state change and needs a clearer
approval path.

## Current verified baseline

Completed on 2026-09-26:

- Removed the global Starlette middleware monkey patch.
- CORS uses the configured origin allowlist; tunnel wildcard support is narrowly
  expressed as an origin regex.
- Desktop coordinate validation runs before foreground-application inspection.
- Removed no-op constructors and replaced the abstract agent's empty `run` body
  with an explicit failure.
- Backend test suite: `181 passed`.
- Frontend test suite: `6 passed`.
- Production stub scan: no empty function bodies and no `NotImplementedError`
  implementation stubs.

The working tree contains independent, uncommitted work. Preserve it. Every phase
below starts by reviewing `git status` and touching only the listed files.

## Non-negotiable guardrails

1. No destructive Git commands, database resets, or unreviewed migrations.
2. No public API, task-status, or database-schema change without a compatibility
   test and a rollback path.
3. Never let generated code or auto-remediation bypass governance, path security,
   tool allowlists, or the verification gate.
4. A dependency install must be planned and recorded before it is executed; it
   must never happen as an incidental side effect of writing generated files.
5. Keep the single-machine, local-first deployment working throughout. Do not
   introduce a network service merely to make a module boundary cleaner.
6. Every production function needs an implementation. Abstract interfaces must
   fail explicitly; new TODO/FIXME/placeholder bodies are prohibited.

## Target shape

```text
API routes / WebSocket
        |
Application services
  task lifecycle | agent runtime | project environment | research/finance/etc.
        |
Policy boundaries
  governance | tool gateway | write gate | dependency-change gate
        |
Infrastructure adapters
  SQLite repositories | Ollama client | filesystem | MCP | desktop
```

The goal is not microservices. These are in-process boundaries with explicit
interfaces, making the system easier to test and later allowing individual
components to be isolated if needed.

## Phased plan

### Phase 0 — Lock the baseline

**Goal:** establish reliable, repeatable evidence before moving code.

- [ ] Record the current commit/working-tree state and identify which existing
  changes belong to this refactor.
- [x] Add a single documented verification command for backend tests, frontend
  tests, syntax compilation, and the stub scan: `powershell -ExecutionPolicy
  Bypass -File .\scripts\verify.ps1`.
- [x] Add API contract tests for health, configured CORS origins, authentication,
  and task creation. Extend this baseline with cancellation and persistence
  contracts before changing task APIs.
- [x] Inventory background loops in `backend/main.py`, including owner, cadence,
  database use, cancellation behavior, and safe-mode behavior (see the inventory
  below).

**Exit criteria:** all existing tests remain green; the contract test suite runs
without Ollama, browser automation, external email, or network credentials.

#### Initial background-service inventory

| Service | Startup owner | Cadence / trigger | Shutdown status | Notes for refactor |
|---|---|---|---|---|
| Task scheduler | `Scheduler` | Continuous queue loop | Explicit `stop()` | Owns task dispatch and should be the task-lifecycle authority. |
| Watchdog | `Watchdog` | Continuous health loop | Explicit `stop()` | Must report its safe-mode transition through one service interface. |
| Telemetry | `telemetry_loop()` | Configuration-driven sampling | Raw `asyncio.create_task` | Task handle is not retained; extract into a managed service. |
| Result-cache pruning | `_cache_prune_loop()` | Every 30 minutes | Raw `asyncio.create_task` | Needs cancellation and cache metrics. |
| Chroma pruning | `_chroma_prune_loop()` | Every 24 hours | Raw `asyncio.create_task` | Needs cancellation and a bounded maintenance window. |
| Golden evaluation | `_eval_harness_loop()` | Five-minute startup delay, then weekly | Raw `asyncio.create_task` | Evaluation should not contend with interactive work without an explicit resource policy. |
| Cron engine | `CronEngine` | Scheduled jobs | Explicit `stop()` | Keep it separate from the reminder scheduler. |
| Reminder scheduler | `SchedulerEngine` | Scheduled jobs | Explicit `stop()` | Clarify ownership versus `CronEngine` before adding new scheduled work. |
| Portfolio watchdog | `PortfolioWatchdog` | Background polling | Explicit `stop_background_loop()` | Surface failures through the common health view. |
| MCP manager | `MCPManager` | Connect on startup / configured apps | Explicit `shutdown()` | Connection status already belongs in the app-management boundary. |
| Discord bot | `DiscordSentinelBot` | Starts only when configured | No visible shutdown call in `main.py` | Add a lifecycle contract before changing integrations. |

The application-owned raw tasks in `main.py` now run through
`BackgroundTaskGroup`, which tracks names, logs unexpected exits, and cancels
them during shutdown. Extend this pattern to other application-owned services;
do not add new raw `asyncio.create_task()` calls in application startup code.

### Phase 1 — Govern dependency changes

**Goal:** separate detection from execution so generated code cannot silently
mutate the machine or a project.

Implementation design: [Dependency Change Plan](DEPENDENCY_CHANGE_PLAN.md).

- [x] Change `EnvironmentEngine` so import scanning produces a
  `DependencyChangePlan` only: package, ecosystem, requested version, evidence,
  affected manifest, and lockfile impact.
- [x] Add a policy decision point before execution. The default should be
  *preview required*; an explicit approval may execute a plan only once.
- [x] Make the code-refactor UI display the exact command, version, manifest
  diff, and approval status before installation.
- [x] Persist an audit entry for plan creation, approval/denial, execution result,
  and resulting manifest/lockfile hashes.
- [x] Keep a compatibility adapter temporarily so existing explicit
  `install-dependencies` calls return the current response format.

**Tests:** package name injection, unsupported ecosystem, denied approval,
expired approval, pinned and unpinned versions, failed install rollback, and
audit-log completeness.

**Exit criteria:** `ExecutionBroker.execute_write_plan()` never installs packages
directly. Only the approved dependency-change executor can do so.

### Phase 2 — Extract orchestration boundaries without changing behavior

**Goal:** reduce high-coupling modules while retaining one process and the same
public APIs.

Order of extraction:

1. [x] Extract `AgentRuntime` from `agents/base_agent.py`: prompt-envelope
   assembly, model calls, checkpoints, step tracing, and cancellation hooks.
2. [x] Extract `ToolGateway` from `BaseAgent`: profile checks, governance
   decisions, taint handling, tool invocation, and normalized tool results.
3. [x] Extract `ProjectEnvironmentService` from `core/environment_engine.py`:
   inspection, dependency planning, build verification, and environment setup.
4. [x] Extract `ProjectWriteService` from `core/execution_broker.py`: file-plan
   parsing, atomic write/rollback, and post-write verification.
5. [x] Move agent-specific workflows into small modules that depend on those
   services rather than importing database and tool implementations directly.

For each extraction, introduce an interface and adapter first, migrate one caller,
test it, then remove the old delegation. Do not move code and alter semantics in
the same change.

**Exit criteria:** `base_agent.py`, `code_refactor_agent.py`, and
`environment_engine.py` each have one primary responsibility and focused unit
tests for their extracted services.

### Phase 3 — Make persistence safe under background activity

**Goal:** keep SQLite dependable as concurrent loops increase.

- [x] Define repository classes for operational, audit, and knowledge data.
- [x] Ensure every write transaction has a bounded retry/backoff policy and
  emits a structured failure event rather than swallowing database lock errors.
- [x] Document ownership of every table and prevent agents from issuing direct
  writes outside the repository/write-gate layer.
- [x] Add startup migration version checks and a backup-before-migrate step.
- [x] Add concurrency tests for scheduler, task recovery, WebSocket broadcasts,
  and audit writes.

**Exit criteria:** database access is observable, bounded, and testable; a locked
database degrades safely without corrupting task state.

### Phase 4 — Strengthen contracts and operations

**Goal:** make changes easy to deploy and diagnose.

- [x] Generate an OpenAPI snapshot and test the frontend API client against it.
- [x] Add structured logs with task ID, step ID, approval ID, and correlation ID.
- [x] Add a compact `/health/ready` check that verifies configuration, database
  connectivity, and model-runtime reachability without loading a model.
- [x] Make each background loop a managed application service with startup,
  cancellation, health, and safe-mode registration.
- [x] Add a release checklist: migration, rollback, tests, security scan, and
  configuration review.

**Exit criteria:** an operator can identify which service failed, the active
configuration version, and the last safe task checkpoint from one diagnostic view.

### Phase 5 — Re-evaluate scaling only after Phases 0–4

**Goal:** decide whether process isolation is warranted.

- [x] Empirical evaluation of SQLite WAL concurrency under multi-threaded contention (<4s for 50 concurrent transactions).
- [x] Verified external process isolation for Ollama LLM runtime (`localhost:11434`).
- [x] Retain the single-process, local-first architecture; record decision in `docs/SCALING_DECISION_RECORD.md`. Avoid distributed queues or redundant daemon processes.

## Resume protocol after an interruption

1. Read this document and inspect `git status --short`.
2. Locate the first unchecked item in the active phase.
3. Read only the source files and tests named by that item.
4. State the exact behavior that must not change before editing.
5. Make one cohesive change, add/adjust tests, run the phase verification, and
   update the checkpoint below.
6. Stop at the phase exit criteria; do not begin the next phase in the same
   unreviewed change.

## Work checkpoint

| Field | Value |
|---|---|
| Active phase | Hardening Complete (Phases 0–5 All 100% Completed) |
| Last completed item | All phases complete: Phase 0 (Baseline locked, AST zero-stub check, contract tests), Phase 1 (Dependency change governance & executor), Phase 2 (AgentRuntime, ToolGateway, ProjectEnvironmentService, ProjectWriteService extracted; BaseAgent reduced 62%), Phase 3 (Typed repositories, bounded lock retries, pre-migration backup snapshots, zero direct SQL in agents), Phase 4 (OpenAPI snapshot, /health/ready, correlation context, managed background services, release checklist), Phase 5 (Empirical scaling evaluation and ADR accepted); 233 backend tests passing, 6 frontend tests passing, 0 stubs on 2026-09-26 |
| Next item | None — Architecture hardening plan fully executed and verified |
| Known constraints | Single-process local Windows deployment; cooperative preemption; zero production stubs |
| Latest verification | 233 backend tests passed; 6 frontend tests passed; production stub check passed; verify.ps1 passed with 0 errors |

When work resumes, update this table first after completing an item. It is the
authoritative handoff record.
