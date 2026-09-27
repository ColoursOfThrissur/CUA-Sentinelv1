# CUA-Sentinel Architecture Blueprints (High-Legibility Edition)

This document provides modular, high-contrast, standard-font-size architecture diagrams for CUA-Sentinel.

---

## 1. Main System Architecture (Standard 16px Font)

```mermaid
%%{init: {'theme': 'neutral', 'themeVariables': { 'fontSize': '16px', 'fontFamily': 'ui-sans-serif, system-ui, sans-serif', 'lineColor': '#4f46e5' }}}%%
flowchart TD
    Client["🖥️ Frontend: React 18 + Vite Dashboard\n(Zustand Store · Typed Axios API · WebSocket)"]
    Gateway["⚙️ API Gateway: FastAPI Server\n(Auth Middleware · Correlation Context · /health/ready · OpenAPI 3.1)"]
    Orchestration["🧩 Agent Orchestration: AgentRuntime + ToolGateway\n(Prompt Envelopes · Defanging · Step Checkpoints · Risk L0-L3)"]
    Services["🔄 Background Services: ServiceManager\n(Task Scheduler · Watchdog & Safe Mode · Telemetry · Pruning)"]
    Tooling["🛠️ Tooling & Execution Engine\n(ProjectWriteService · ProjectEnvironmentService · DependencyChangeExecutor)"]
    Storage["💾 Persistence Tier: 4x SQLite (WAL Mode)\n(operational.sqlite · audit.sqlite · knowledge.sqlite · state.sqlite)"]
    Inference["🧠 Local Model Runtime: Ollama Server (Port 11434)\n(ModelManager · VRAM Admission · Qwen3 14B Q4 · Phi-3 Mini)"]

    Client -->|HTTP / WebSocket| Gateway
    Gateway --> Orchestration
    Gateway --> Services
    Orchestration --> Tooling
    Orchestration --> Storage
    Services --> Storage
    Orchestration -->|Inference Stream| Inference
    Tooling --> Storage
```

---

## 2. Agent Execution & Tool Gateway Subsystem

```mermaid
%%{init: {'theme': 'neutral', 'themeVariables': { 'fontSize': '16px', 'fontFamily': 'ui-sans-serif, system-ui, sans-serif' }}}%%
flowchart TD
    A["1. Queue Task Claim\n(P0 Preemption to P2)"] --> B["2. Assemble Prompt Envelope\n(System Rules · Task · Facts · Defanged Inputs)"]
    B --> C["3. Model Inference\n(Ollama via ModelManager)"]
    C --> D["4. Tool Call Parsing\n(JSON Arguments Extraction)"]
    D --> E{"5. Profile Permissions Check\n(Is Tool Registered & Allowed?)"}
    E -- Allowed --> F{"6. Taint & Risk Policy Check\n(Is Task Tainted? Risk L0-L3?)"}
    E -- Denied --> J["Gateway Denial & Audit Log"]
    F -- "L0 / L1 Safe" --> G["7. Execute Tool Handler"]
    F -- "L2 / L3" --> H{"Human Approval Valid?"}
    H -- Approved --> G
    H -- Pending --> K["Request HITL Approval"]
    G --> L["8. Record Audit Log\n(execute_write_transaction)"]
    L --> M["9. Commit Task Checkpoint\n(Durable Resumption State)"]
```

---

## 3. Governed Dependency Change Pipeline

```mermaid
%%{init: {'theme': 'neutral', 'themeVariables': { 'fontSize': '16px', 'fontFamily': 'ui-sans-serif, system-ui, sans-serif' }}}%%
flowchart TD
    D1["1. AST Import Scanning\n(ProjectEnvironmentService detects new imports)"] --> D2["2. Build DependencyChangePlan\n(PEP 508 / npm validation + Manifest SHA-256 hash)"]
    D2 --> D3["3. Persist Plan with Status = 'REQUESTED'\n(DependencyPlanRepository)"]
    D3 --> D4["4. Operator Review in UI\n(DependencyPlansModal preview)"]
    D4 --> D5{"5. Operator Decision"}
    D5 -- Approved --> D6["6. DependencyChangeExecutor Lock\n(Single Authorized Installer)"]
    D5 -- Rejected --> D10["Mark Plan REJECTED"]
    D6 --> D7["7. Backup Manifests\n(.sentinel_backup/deps/)"]
    D7 --> D8["8. Run Package Manager\n(pip install / npm install)"]
    D8 --> D9{"9. Post-Install Build Gate"}
    D9 -- Passes --> D11["Compute Post-Hash & Mark COMPLETED"]
    D9 -- Fails --> D12["Restore Backup Manifest & Auto-Rollback"]
```

---

## 4. SQLite Multi-Database Persistence Tier

```mermaid
%%{init: {'theme': 'neutral', 'themeVariables': { 'fontSize': '16px', 'fontFamily': 'ui-sans-serif, system-ui, sans-serif' }}}%%
flowchart TD
    Callers["Application Callers\n(Agent Runtime · Tool Gateway · Background Loops · REST API)"] --> Repos["Typed Repository Tier\n(OperationalRepository · AuditRepository · KnowledgeRepository)"]
    Repos --> TxLayer["Write Resilience Layer\n(execute_write_transaction context manager)"]
    TxLayer --> RetryCheck{"SQLite Lock / Busy?"}
    RetryCheck -- "Contention" --> Backoff["Bounded Backoff: 1 to 5 retries\n(0.05s -> 0.10s -> 0.20s -> 0.40s -> 0.80s + jitter)"]
    Backoff --> TxLayer
    RetryCheck -- "Exhausted" --> LockError["Raise DatabaseLockError\n(Emits DB_WRITE_TRANSACTION_FAILED Event)"]
    RetryCheck -- "Success" --> DBs[("SQLite Databases in WAL Mode (timeout=30s)\n• operational.sqlite (Tasks, Steps, Checkpoints)\n• audit.sqlite (Audit Logs, HITL, System Events)\n• knowledge.sqlite (Episodic Memory, Claims, Docs)\n• state.sqlite (Finance Facts, Entities, State Events)")]
```
