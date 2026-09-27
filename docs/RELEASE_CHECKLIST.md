# CUA-Sentinel Production Release & Deployment Checklist

This document defines the strict gate verification procedure required prior to deploying updates to CUA-Sentinel.

---

## 1. Pre-Release Verification Gates

Before tagging, packaging, or deploying:

- [ ] **Unified Verification Script**:
  Run from repository root:
  ```powershell
  powershell -ExecutionPolicy Bypass -File .\scripts\verify.ps1
  ```
  Must output:
  - `Production stub check passed` (0 stubs, 0 unhandled `NotImplementedError` or `TODO` bodies in production code).
  - All backend unit and integration tests passing (`pytest backend/tests`).
  - All frontend unit tests passing (`vitest run --run`).
  - Exit code `0`.

- [ ] **API Contract & Schema Alignment**:
  - Run `backend/tests/test_api_client_contract.py`.
  - Confirm `docs/openapi.json` is updated and matches frontend `src/api/index.ts`.
  - Verify `/health/ready` responds with `HTTP 200` and `"status": "ready"`.

- [ ] **Architectural Invariant Checks**:
  - Ensure zero raw SQL statements in `backend/agents/` (`test_architectural_rule_zero_direct_sql_in_agents`).
  - Ensure all database writes go through `OperationalRepository`, `AuditRepository`, `KnowledgeRepository`, `write_gate`, or `execute_write_transaction`.
  - Ensure dependency modifications strictly require `DependencyChangePlan` approval and cannot be executed directly by `ExecutionBroker`.

---

## 2. Database Migration & Rollback Procedure

- [ ] **Pre-Migration Automatic Backup**:
  - `initialize_all_databases()` automatically creates pre-migration timestamped backups in `data/.sentinel_backup/db_pre_migrate/` before applying schema migrations.
  - Verify backup snapshots exist if existing databases are being updated.

- [ ] **Rollback Procedure**:
  If a release fails during or immediately after startup:
  1. Stop sentinel services: `.\stop.bat`.
  2. Inspect backup directory:
     ```powershell
     Get-ChildItem -Path data\.sentinel_backup\db_pre_migrate\
     ```
  3. Restore SQLite database snapshot to `data/<name>.sqlite`.
  4. Git revert the deployment branch/commit:
     ```powershell
     git checkout <last-known-good-commit>
     ```
  5. Restart services: `.\launch.bat`.

---

## 3. Configuration & Security Audit Review

- [ ] **Configuration Integrity**:
  - Verify `backend/config/system_config.json`: valid JSON, allowed CORS origins configured, no wildcards combined with credentials.
  - Verify `backend/config/models_registry.json`: valid model definitions and active endpoints.
  - Verify `backend/config/policy_rules.json`: governance rules present and valid JSON.
  - Verify `.env`: no exposed secrets or API keys checked into version control.

- [ ] **Safe-Mode & Watchdog Verification**:
  - Verify watchdog monitoring loop is active.
  - Verify `/api/settings/system/safe-mode` can toggle safe mode, halting L2/L3 execution while allowing L0 read tools.
  - Verify emergency stop `/api/settings/system/emergency-stop` halts running agent steps safely.
