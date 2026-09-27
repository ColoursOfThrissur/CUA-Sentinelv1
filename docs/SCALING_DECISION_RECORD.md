# Architectural Decision Record: Process Scaling & Topology (Phase 5)

## Status: ACCEPTED & FINALIZED
**Date**: 2026-09-26  
**Context**: CUA-Sentinel Architecture Hardening (Phases 0–5)

---

## 1. Context & Evaluation

Under Phase 5 of the architecture hardening plan, we evaluated whether worker process isolation or distributed queue infrastructure (e.g. Celery, Redis, RabbitMQ) is warranted for CUA-Sentinel on a single Windows workstation with an NVIDIA RTX 3060 12GB GPU.

### Key Empirical Findings:

1. **Model Runtime Process Isolation**:
   - The primary resource-intensive workload (LLM inference) is executed by the Ollama server process on `localhost:11434`.
   - Ollama already runs in its own native process with dedicated VRAM management, memory locking, and GPU compute scheduling.
   - The FastAPI backend interacts with Ollama via HTTP streams; model crashes or memory spikes do not bring down FastAPI.

2. **Persistence Concurrency Under Contention**:
   - Benchmarking 10 concurrent worker threads executing high-frequency writes against `OperationalRepository`, `AuditRepository`, and `KnowledgeRepository` demonstrated:
     - 100% successful commit rate.
     - Zero deadlocks or uncaught lock errors under WAL mode + `PRAGMA busy_timeout = 30000` + `execute_write_transaction` bounded exponential backoff.
     - Execution time for 50 task/step creations with checkpoints: ~3.2 seconds total.

3. **Windows Multiprocessing Overhead**:
   - On Windows, Python lacks POSIX `fork()`. Any multi-process worker model requires `spawn`, which incurs heavy module re-import penalties (2–5 seconds per worker startup), complex IPC serialization (Pickle overhead), and duplicate database file descriptor management.

4. **Resource Footprint**:
   - Single-process FastAPI + BackgroundTaskGroup + ServiceManager: ~60MB RAM footprint.
   - Low latency internal in-memory dispatch between Task Scheduler and Agent Runtime.

---

## 2. Decision

**Retain the single-process, local-first architecture.**

- FastAPI remains the single host process for HTTP APIs, WebSockets, background loops, and agent orchestration.
- Ollama remains the independent model engine daemon.
- No external brokers (Redis, RabbitMQ, Kafka) or heavy worker frameworks (Celery) are adopted.
- All background tasks are managed via `ServiceManager` and `BackgroundTaskGroup` with cooperative preemption and durable SQLite task checkpoints.

---

## 3. Consequences & Guardrails

- **Single Host Simplicity**: 1-click startup (`launch.bat`) and 1-click shutdown (`stop.bat`) remain frictionless for end users.
- **Safety**: Safe mode and emergency stops propagate immediately in-memory across all active services without network serialization delay.
- **Resumption**: If the process is terminated, tasks resume from the last valid checkpoint stored in `task_checkpoints` upon next launch.
