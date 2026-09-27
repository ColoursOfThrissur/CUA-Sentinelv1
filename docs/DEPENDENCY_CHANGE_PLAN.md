# Dependency Change Plan

**Status:** Design approved for implementation planning  
**Last updated:** 2026-09-26

This document defines the boundary between discovering a missing dependency and
installing it. It intentionally does not change current installation behavior;
implementation begins only after the data model and approval semantics below are
covered by tests.

## Objective

Generated code, repairs, or import scans may identify missing packages, but they
must not install them as an incidental side effect. A dependency change becomes a
durable, reviewable plan and may execute only after a one-time approval.

## Lifecycle

```text
SCAN -> PLANNED -> AWAITING_APPROVAL -> APPROVED -> EXECUTING
                                      |              |
                                      v              v
                                   REJECTED       SUCCEEDED / FAILED / EXPIRED
```

- `SCAN` is read-only import and manifest analysis.
- `PLANNED` contains a deterministic diff and version resolution; it performs no
  package-manager command.
- `AWAITING_APPROVAL` is shown in the UI and registered with HITL.
- `APPROVED` is a single-use authorization bound to a plan hash and expiry.
- `EXECUTING` runs the exact approved command in the target project only.
- `SUCCEEDED` captures final manifest/lockfile hashes. `FAILED` retains logs and
  does not retry automatically. `EXPIRED` requires a newly generated plan.

## Plan payload

`DependencyChangePlan` must include:

| Field | Purpose |
|---|---|
| `plan_id` | Immutable unique identifier |
| `project_path` | Canonical, authorized project root |
| `ecosystem` | `pip` or `npm` only |
| `package_name` / `requested_spec` | Validated package and resolved version constraint |
| `reason` / `evidence` | Import source, build error, or explicit user request |
| `manifest_path` / `lockfile_path` | Files expected to change |
| `manifest_before_hash` / `lockfile_before_hash` | Pre-execution concurrency guard |
| `planned_command` | Tokenized command for display and execution; never shell text |
| `risk_level` | Controlled mutation; approval is mandatory for this workflow |
| `plan_hash` | Hash of all approval-relevant fields |
| `created_at` / `expires_at` | Plan lifetime |
| `status` / `result` | Lifecycle and sanitized outcome |

Do not store secret environment values, full package-manager output containing
credentials, or raw untrusted build logs in the plan payload.

## Approval rules

1. Approval binds to `plan_id`, `plan_hash`, target root, and command tokens.
2. An approval expires after 15 minutes and is consumed exactly once.
3. Any manifest/lockfile hash mismatch invalidates the plan before execution.
4. A plan with an unpinned version is displayable but cannot execute until the
   user explicitly confirms that version resolution is acceptable.
5. The executor uses argument arrays with `shell=False`; neither package names
   nor version specs are interpolated into shell command strings.
6. Failure does not roll back a package-manager operation automatically. It
   reports the changed files and offers a separate, explicitly approved rollback
   action based on a backup captured before execution.

## Integration points

- `EnvironmentEngine` becomes an inspector and plan builder. It no longer calls
  a package manager from `scan_and_install_dependencies`.
- `ExecutionBroker` may request a scan after writing files, but it only records
  plans; it cannot execute them.
- The code-refactor route returns dependency-plan IDs rather than an installation
  result when remediation identifies missing packages.
- A dedicated executor is the sole location allowed to invoke `pip` or `npm`.
- The existing HITL/audit infrastructure records plan creation, approval,
  execution, failure, expiry, and rollback requests.

## Initial API surface

| Method | Path | Behavior |
|---|---|---|
| `GET` | `/api/dependency-plans` | List plans scoped to authorized projects |
| `GET` | `/api/dependency-plans/{plan_id}` | Show a plan and immutable evidence |
| `POST` | `/api/dependency-plans/{plan_id}/approve` | Create one-time approval after plan-hash validation |
| `POST` | `/api/dependency-plans/{plan_id}/execute` | Execute an approved, unexpired plan |
| `POST` | `/api/dependency-plans/{plan_id}/reject` | Mark plan rejected with optional reason |

Do not add these routes until plan persistence and the executor are covered by
unit and integration tests.

## Implementation sequence

1. Add a migration and repository with no callers.
2. Add plan-builder validation tests: input/package injection, canonical paths,
   pin resolution, manifest hash, and expiry.
3. Add approval tests: one-time use, stale hash, denied, expired, and audit row.
4. Add executor tests using a fake process runner, including backup creation and
   failure reporting.
5. Migrate explicit `install-dependencies` requests to plan creation plus approval.
6. Remove direct package-manager calls from automatic remediation and
   `ExecutionBroker` only after compatibility tests pass.

## Resume checkpoint

The next implementation task is item 1: introduce the persistence schema and a
repository with no route or auto-remediation caller. This is intentionally
non-behavior-changing and should be committed as its own change.
