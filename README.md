<p align="center">
  <img src="sentinel.ico" alt="CUA-Sentinel" width="100" />
</p>

<h1 align="center">🛡️ CUA-Sentinel</h1>
<p align="center">
  <strong>Self-Hosted Autonomous AI Command Center for Windows</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.12-blue?logo=python&logoColor=white" alt="Python 3.12" />
  <img src="https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white" alt="FastAPI" />
  <img src="https://img.shields.io/badge/React-18.3-61DAFB?logo=react&logoColor=black" alt="React 18" />
  <img src="https://img.shields.io/badge/TypeScript-5.6-3178C6?logo=typescript&logoColor=white" alt="TypeScript" />
  <img src="https://img.shields.io/badge/Ollama-Local_LLMs-black?logo=ollama" alt="Ollama" />
  <img src="https://img.shields.io/badge/NVIDIA-RTX_3060_12GB-76B900?logo=nvidia&logoColor=white" alt="NVIDIA GPU" />
  <img src="https://img.shields.io/badge/platform-Windows-0078D6?logo=windows&logoColor=white" alt="Windows" />
  <img src="https://img.shields.io/badge/license-MIT-green" alt="License" />
</p>

<p align="center">
  A fully local, privacy-first AI command center that runs 8 LLM models on your own hardware.<br/>
  One-click launch. No cloud dependencies. No API keys required.
</p>

---

## 📋 Table of Contents

- [Architecture](#-architecture)
- [Features](#-features)
- [Prerequisites](#-prerequisites)
- [Quick Start](#-quick-start)
- [Desktop Shortcut](#-desktop-shortcut)
- [Configuration](#-configuration)
- [Tech Stack](#-tech-stack)
- [Project Structure](#-project-structure)
- [API Reference](#-api-reference)
- [Model Registry](#-model-registry)
- [Governance & Safety](#-governance--safety)
- [License](#-license)

---

## 🏗 Architecture

CUA-Sentinel follows a **3-tier architecture** with all inference running locally on your GPU:

```
┌─────────────────────────────────────────────────────────────────┐
│                    🖥️  React Dashboard (:5173)                  │
│          Vite · TypeScript · Tailwind · Zustand · Recharts      │
│            WebSocket real-time · 13 component modules           │
├─────────────────────────────────────────────────────────────────┤
│                                 ▲ REST + WebSocket              │
│                                 ▼                               │
├─────────────────────────────────────────────────────────────────┤
│                   ⚙️  FastAPI Backend (:8000)                    │
│    8 Agents · 38 Core Modules · 15 API Routes · 8 Tools        │
│  Task Queue · Scheduler · Watchdog · Governance · Discord Bot   │
├─────────────────────────────────────────────────────────────────┤
│                                 ▲ HTTP (:11434)                 │
│                                 ▼                               │
├─────────────────────────────────────────────────────────────────┤
│                     🧠  Ollama LLM Runtime                      │
│       8 Models · VRAM Admission Control · Hot-Swap Loading      │
│             RTX 3060 12GB · Q4_K_M Quantization                 │
├─────────────────────────────────────────────────────────────────┤
│                        💾  Storage Layer                         │
│    3× SQLite (operational · audit · knowledge) · ChromaDB       │
└─────────────────────────────────────────────────────────────────┘
```

---

## ✨ Features

### 💬 Conversational AI
- Multi-turn chat with web search integration and research synthesis
- Intent classification routes to specialized agents automatically
- Conversation memory with persistent session context

### 🔧 Autonomous Code Refactoring & Scaffolding
- AST-based code analysis with security auditing
- Full project scaffolding from natural language descriptions
- Automated code health evaluation, diff engine, and alignment validation
- Multi-agent pipeline: Scaffolder → Tester → Reviewer → Refactor

### 📝 In-Browser IDE (Canvas)
- File tree explorer with full read/write access
- Integrated code editor with syntax awareness
- Alignment validation against project conventions

### 💰 Personal Finance Portfolio
- Import holdings from Excel/CSV files
- Live stock quotes via Yahoo Finance
- Portfolio watchdog with background price monitoring
- Track gains, alerts, and asset allocation

### 📧 Gmail Inbox Triage
- IMAP-based inbox scanning and categorization
- AI-powered email classification and priority assignment
- Actionable feed with summarized recommendations

### 🧠 Second Brain (Link Bookmarking + RAG)
- Save and categorize links with AI-generated summaries
- ChromaDB vector store for semantic similarity search
- Retrieval-augmented generation for contextual recall

### 🤖 Discord Bot Remote Control
- 2-way Discord bot for remote command execution
- Commands: `!price`, `!health`, `!refactor`, `!task`, and more
- User-scoped access control with allowed user ID filtering

### 📊 Hardware Telemetry Dashboard
- Real-time CPU, RAM, GPU temperature, and VRAM monitoring
- WebSocket-powered live telemetry stream (10s sample interval)
- Hourly and daily rollup aggregation for trend analysis

### 🛡️ Human-in-the-Loop Governance
- **L0 – Read Only**: File reads, web search, DB queries (auto-approved)
- **L1 – Local Write**: Sandbox file creation (auto-approved, logged)
- **L2 – Project Mutation**: Git commits, package installs (auto-approved, logged, notified)
- **L3 – Destructive/External**: Git push, deploys, deletions (requires human approval)

### ⚡ Task Queue & Scheduling
- Priority-based preemptive task scheduling
- Auto-recovery of interrupted tasks on restart
- Configurable retry policies per error class (syntax, network, auth, etc.)
- Cron engine for recurring background jobs
- Circuit-breaker watchdog with safe-mode fallback

---

## 📦 Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| **Python** | 3.12+ | With `pip` and `venv` support |
| **Node.js** | 18+ | With `npm` |
| **Ollama** | Latest | [ollama.com](https://ollama.com) |
| **NVIDIA GPU** | RTX 3060 12GB+ recommended | CUDA-capable; CPU-only works but slower |
| **Windows** | 10/11 | Primary supported platform |
| **Git** | 2.40+ | For project management features |

### Pull Required Ollama Models

```bash
ollama pull qwen3:14b-q4_K_M
ollama pull qwen3.5:9b
ollama pull qwen2.5-coder:14b
ollama pull qwen2.5-coder:latest
ollama pull qwen3-vl:8b
ollama pull mistral:7b
ollama pull phi3:latest
ollama pull llava:7b
```

---

## 🚀 Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/ColoursOfThrissur/CUA-Sentinelv1.git
cd CUA-Sentinelv1
```

### 2. Set up the backend

```bash
# Create and activate virtual environment
python -m venv .venv
.venv\Scripts\activate

# Install Python dependencies
pip install -r backend/requirements.txt
```

### 3. Set up the frontend

```bash
cd frontend
npm install
cd ..
```

### 4. Configure environment

```bash
# Copy the example env file and edit with your values
copy backend\.env.example backend\.env
```

Edit `backend/.env` with your settings:

```env
SENTINEL_API_TOKEN=your_secure_token_here
SENTINEL_JWT_SECRET=generate_with_python_secrets
SENTINEL_CF_TOKEN=               # Optional: Cloudflare Tunnel
SENTINEL_VAPID_PUBLIC=           # Optional: Web Push notifications
SENTINEL_VAPID_PRIVATE=          # Optional: Web Push notifications
```

> 💡 Generate a JWT secret: `python -c "import secrets; print(secrets.token_hex(32))"`

### 5. Launch everything

```bash
# One-click launch (starts Ollama → Backend → Frontend → Browser)
launch.bat
```

The launcher will:
1. ✅ Start Ollama AI service on port `11434`
2. ✅ Start FastAPI backend on port `8000`
3. ✅ Start Vite dev server on port `5173`
4. ✅ Open your browser to `http://localhost:5173`

---

## 🖥️ Desktop Shortcut

Create a 1-click Desktop shortcut for instant launch:

1. **Right-click** on your Desktop → **New** → **Shortcut**
2. Set target to: `C:\path\to\CUA-Sentinel\launch.bat`
3. Set "Start in" to: `C:\path\to\CUA-Sentinel`
4. **Change icon**: Browse to `sentinel.ico` in the project root
5. Name it **CUA-Sentinel**

### Available Launch Scripts

| Script | Purpose |
|---|---|
| `launch.bat` | 🟢 **Primary launcher** — starts all services via `scripts/launcher.py`, opens browser, keeps window open for monitoring |
| `start.bat` | 🔵 **Production build** — runs `npm build`, starts backend, optionally starts Cloudflare Tunnel |
| `stop.bat` | 🔴 **Graceful shutdown** — cleanly stops all Sentinel services via `scripts/stop_services.py` |

---

## ⚙️ Configuration

All configuration lives in `backend/config/` with three JSON files:

### `system_config.json`
Core system settings including API host/port, scheduler tuning, storage limits, and telemetry intervals.

| Section | Key Settings |
|---|---|
| `system` | `worker_id`, `os_type`, `version` |
| `ollama` | `base_url` (`:11434`), `request_timeout_sec` (300), `keep_alive` (15m) |
| `api` | `port` (8000), `cors_origins`, `token_expiry_hours` (720) |
| `scheduler` | `poll_interval_sec` (5), `max_task_retries` (5), `aging_boost_per_hour` (1.0) |
| `watchdog` | `heartbeat_check_interval_sec` (30), `circuit_breaker_cooldown_sec` (600) |
| `storage` | `max_workspace_size_mb` (2048), `sandbox_ttl_days` (7) |
| `telemetry` | `hardware_sample_interval_sec` (10), hourly/daily rollups |
| `auto_remediation` | Auto-install missing libs, trigger on crashes/build failures/AST vulnerabilities |

### `models_registry.json`
Defines all 8 LLM models with VRAM budgets, capabilities, and agent routing.

| Model | Tag | VRAM | Role |
|---|---|---|---|
| Qwen3 14B Q4 | `qwen3:14b-q4_K_M` | ~8.4 GB | Primary universal (reasoning, coding, research) |
| Qwen3.5 9B | `qwen3.5:9b` | ~6.6 GB | Reasoning fallback |
| Qwen2.5 Coder 14B | `qwen2.5-coder:14b` | ~8.4 GB | Primary coding model |
| Qwen2.5 Coder 7B | `qwen2.5-coder:latest` | ~4.7 GB | Lightweight coding |
| Qwen3 VL 8B | `qwen3-vl:8b` | ~6.1 GB | Vision / desktop verification |
| Mistral 7B | `mistral:7b` | ~4.4 GB | Summarization & synthesis |
| Phi-3 Mini | `phi3:latest` | ~2.2 GB | Sanitizer & classifier (fast) |
| LLaVA 7B | `llava:7b` | ~4.7 GB | Backup vision model |

Hardware limits: **12,288 MB VRAM** max, **1,536 MB** OS reserve, single inference concurrency with hot-swap model loading.

### `policy_rules.json`
Governance rules with L0–L3 risk tiers, tool-level policies, retry strategies, and safe-mode triggers.

---

## 🛠 Tech Stack

### Backend

| Technology | Version | Purpose |
|---|---|---|
| Python | 3.12 | Runtime |
| FastAPI | 0.115.0 | REST API framework |
| Uvicorn | 0.30.6 | ASGI server |
| Pydantic | 2.9.2 | Data validation & settings |
| SQLAlchemy | 2.0+ | ORM (SQLite databases) |
| SQLModel | 0.0.14+ | Model layer |
| ChromaDB | 0.5.15 | Vector store for RAG |
| APScheduler | 3.10.4 | Background task scheduling |
| discord.py | 2.7.1 | Discord bot integration |
| httpx | 0.27.2 | Async HTTP client |
| GitPython | 3.1.43 | Git operations |
| psutil | 6.0.0 | System telemetry |
| openpyxl | 3.1+ | Excel file parsing |
| BeautifulSoup4 | 4.12.3 | Web scraping & sanitization |
| PyAutoGUI | 0.9.54+ | Desktop automation |
| pywin32 | 306 | Windows system integration |

### Frontend

| Technology | Version | Purpose |
|---|---|---|
| React | 18.3 | UI framework |
| TypeScript | 5.6 | Type-safe development |
| Vite | 5.4 | Build tool & dev server |
| Tailwind CSS | 3.4 | Utility-first styling |
| Zustand | 5.0 | State management |
| Recharts | 2.12 | Data visualization & charts |
| React Router | 6.26 | Client-side routing |
| Axios | 1.7 | HTTP client |
| Lucide React | 0.447 | Icon library |
| React Markdown | 9.0 | Markdown rendering |
| Vite PWA | 0.20 | Progressive Web App support |

### Infrastructure

| Technology | Purpose |
|---|---|
| Ollama | Local LLM inference runtime |
| SQLite × 3 | Operational, Audit, Knowledge databases |
| ChromaDB | Vector embeddings for Second Brain RAG |
| WebSocket | Real-time telemetry & live updates |
| Cloudflare Tunnel | Optional secure remote access |

---

## 📁 Project Structure

```
CUA-Sentinel/
├── 📄 launch.bat                  # 1-click launcher (→ scripts/launcher.py)
├── 📄 start.bat                   # Production build + Cloudflare Tunnel
├── 📄 stop.bat                    # Graceful shutdown (→ scripts/stop_services.py)
├── 🖼️ sentinel.ico                # Application icon
│
├── 📂 scripts/
│   ├── launcher.py                # Orchestrates Ollama → Backend → Frontend startup
│   └── stop_services.py           # Clean service termination
│
├── 📂 backend/
│   ├── main.py                    # FastAPI app entry point + lifespan management
│   ├── requirements.txt           # Python dependencies (30 packages)
│   ├── .env.example               # Environment variable template
│   │
│   ├── 📂 config/
│   │   ├── system_config.json     # System, API, scheduler, watchdog settings
│   │   ├── models_registry.json   # 8 LLM models + VRAM budgets + routing
│   │   ├── policy_rules.json      # L0–L3 governance + retry policies
│   │   └── loader.py              # Config file loader
│   │
│   ├── 📂 agents/                 # 8 specialized AI agents
│   │   ├── base_agent.py          # Abstract agent interface
│   │   ├── endpoint_agent.py      # Chat, finance, bookmark routing
│   │   ├── code_refactor_agent.py # AST analysis, scaffolding, refactoring
│   │   ├── researcher.py          # Web research agent
│   │   ├── synthesizer.py         # Research synthesis agent
│   │   ├── cua_agent.py           # Computer-Use Agent (desktop automation)
│   │   ├── project_repair_agent.py# Automated project repair
│   │   └── research_cycle_agent.py# Multi-step research orchestration
│   │
│   ├── 📂 core/                   # 38 core modules
│   │   ├── model_manager.py       # VRAM-aware model loading & hot-swap
│   │   ├── queue.py               # Priority task queue with preemption
│   │   ├── scheduler.py           # Task scheduler with aging boost
│   │   ├── governance.py          # L0–L3 risk tier enforcement
│   │   ├── watchdog.py            # Health monitoring & circuit breaker
│   │   ├── discord_bot.py         # 2-way Discord bot (!price, !health, etc.)
│   │   ├── gmail_triage.py        # IMAP email scanning & categorization
│   │   ├── project_scaffolder.py  # Full-stack project generation
│   │   ├── alignment_validator.py # Code alignment & convention checking
│   │   ├── memory_layers.py       # Multi-layer conversation memory
│   │   ├── intent_classifier.py   # Natural language intent routing
│   │   ├── portfolio_watchdog.py  # Stock price background monitor
│   │   ├── cron_engine.py         # Recurring job scheduler
│   │   ├── scheduler_engine.py    # Reminder & cron background service
│   │   └── ...                    # 24 more modules
│   │
│   ├── 📂 tools/                  # 8 tool implementations
│   │   ├── web_search.py          # DuckDuckGo web search
│   │   ├── file_io.py             # Sandboxed file read/write
│   │   ├── git_tool.py            # Git operations (commit, diff, log)
│   │   ├── finance_tools.py       # Yahoo Finance quotes & portfolio
│   │   ├── memory_tool.py         # ChromaDB vector memory
│   │   ├── link_manager.py        # Second Brain link bookmarking
│   │   ├── browser_tool.py        # Web browsing & scraping
│   │   └── desktop_tool.py        # Desktop automation (PyAutoGUI)
│   │
│   ├── 📂 api/
│   │   ├── server.py              # FastAPI app factory + middleware
│   │   ├── auth.py                # Token authentication
│   │   ├── websocket.py           # WebSocket telemetry broadcast
│   │   └── 📂 routes/             # 15 API route modules
│   │       ├── chat.py            # Conversation endpoints
│   │       ├── tasks.py           # Task CRUD & execution
│   │       ├── projects.py        # Project management
│   │       ├── code_refactor.py   # Refactoring pipeline
│   │       ├── finance.py         # Portfolio & stock quotes
│   │       ├── links.py           # Bookmark management
│   │       ├── gmail_triage.py    # Email triage endpoints
│   │       ├── telemetry.py       # Hardware metrics API
│   │       ├── models.py          # Model management
│   │       ├── hitl.py            # Human approval endpoints
│   │       ├── notifications.py   # Push notification mgmt
│   │       ├── improvements.py    # Code improvement suggestions
│   │       ├── digests.py         # AI digest generation
│   │       ├── scheduler.py       # Cron & reminder management
│   │       └── settings.py        # System settings API
│   │
│   ├── 📂 db/
│   │   ├── connections.py         # SQLite connection manager
│   │   └── 📂 migrations/         # Schema migrations
│   │
│   └── 📂 tests/                  # pytest test suite
│
├── 📂 frontend/
│   ├── package.json               # Node.js dependencies
│   ├── vite.config.ts             # Vite build configuration
│   ├── tailwind.config.js         # Tailwind CSS configuration
│   ├── tsconfig.json              # TypeScript configuration
│   │
│   └── 📂 src/
│       ├── App.tsx                # Root component + routing
│       ├── main.tsx               # React entry point
│       │
│       ├── 📂 store/
│       │   └── index.ts           # Zustand global state
│       │
│       ├── 📂 pages/
│       │   ├── Dashboard.tsx      # Main dashboard view
│       │   ├── TaskDetail.tsx     # Task detail & execution view
│       │   └── Settings.tsx       # System settings page
│       │
│       ├── 📂 components/         # 13 component modules
│       │   ├── 📂 chat/           # Conversational AI interface
│       │   ├── 📂 canvas/         # In-browser IDE
│       │   ├── 📂 coding/         # Code refactoring UI
│       │   ├── 📂 finance/        # Portfolio dashboard
│       │   ├── 📂 gmail/          # Email triage feed
│       │   ├── 📂 links/          # Second Brain bookmarks
│       │   ├── 📂 telemetry/      # Hardware metrics charts
│       │   ├── 📂 tasks/          # Task queue management
│       │   ├── 📂 projects/       # Project management
│       │   ├── 📂 hitl/           # Human approval interface
│       │   ├── 📂 digests/        # AI-generated digests
│       │   ├── 📂 notifications/  # Notification center
│       │   └── 📂 common/         # Shared UI components
│       │
│       └── 📂 api/                # API client layer
│
└── 📂 data/                       # Runtime data (gitignored)
    ├── operational.sqlite         # Tasks, sessions, system state
    ├── audit.sqlite               # Governance audit trail
    ├── knowledge.sqlite           # Second Brain & memory
    ├── 📂 artifacts/              # Generated files & outputs
    ├── 📂 backups/                # Automated backups
    └── 📂 exports/                # Data exports
```

---

## 🔌 API Reference

The backend exposes **15 route modules** at `http://localhost:8000`:

| Endpoint Group | Path Prefix | Description |
|---|---|---|
| Chat | `/api/chat` | Conversational AI with multi-turn context |
| Tasks | `/api/tasks` | Task CRUD, execution, status tracking |
| Projects | `/api/projects` | Project management & health monitoring |
| Code Refactor | `/api/code-refactor` | Refactoring pipeline & AST analysis |
| Finance | `/api/finance` | Portfolio, holdings, stock quotes |
| Links | `/api/links` | Second Brain bookmark management |
| Gmail Triage | `/api/gmail` | Email scanning & categorization |
| Telemetry | `/api/telemetry` | Hardware metrics & system health |
| Models | `/api/models` | LLM model management & status |
| HITL | `/api/hitl` | Human approval queue |
| Notifications | `/api/notifications` | Push notification management |
| Improvements | `/api/improvements` | Code improvement suggestions |
| Digests | `/api/digests` | AI-generated content digests |
| Scheduler | `/api/scheduler` | Cron jobs & reminders |
| Settings | `/api/settings` | System configuration |

**WebSocket**: `ws://localhost:8000/ws/telemetry` — real-time hardware metrics stream

**Health Check**: `GET /health` — service status

---

## 🧠 Model Registry

CUA-Sentinel uses **VRAM admission control** to safely load models within GPU memory limits:

```
Total VRAM:           12,288 MB  (RTX 3060)
OS Reserve:            1,536 MB
Runtime Overhead:        512 MB
Available for Models: 10,240 MB
Concurrency:               1    (hot-swap, one model at a time)
Quantization:          Q4_K_M   (all models)
KV Cache:              Q8_0
```

### Agent → Model Routing

| Agent Role | Routed Model | Capability |
|---|---|---|
| ENDPOINT / FINANCE / BOOKMARK | Qwen3 14B Q4 | General chat & reasoning |
| SCAFFOLDER / REFACTOR / TESTER / REVIEWER | Qwen3 14B Q4 | Code generation & review |
| RESEARCHER / SYNTHESIZER | Qwen3 14B Q4 | Web research & synthesis |
| SECOND_BRAIN / CUA | Qwen3 14B Q4 | Memory & desktop automation |
| SANITIZER | Phi-3 Mini | Fast input sanitization |
| VISION | Qwen3 VL 8B | Image understanding |

---

## 🛡️ Governance & Safety

### Risk Tier Enforcement

| Tier | Label | Approval | Logging | Example Operations |
|---|---|---|---|---|
| **L0** | Read Only | Auto ✅ | — | File reads, web search, DB queries |
| **L1** | Local Write | Auto ✅ | ✅ Logged | Sandbox file writes, memory updates |
| **L2** | Project Mutation | Auto ✅ | ✅ Logged + Notified | Git commits, package installs |
| **L3** | Destructive/External | **Human Required** 🛑 | ✅ Logged + Immediate Alert | Git push, deploys, file deletions |

### Auto-Recovery & Safe Mode

- **Auto-remediation**: Automatically installs missing libraries, recovers from build failures
- **Circuit breaker**: Watchdog detects crash loops and enters cooldown (600s)
- **Safe mode triggers**: GPU driver failures, SQLite corruption, excessive RAM pressure, security violations
- **Safe mode allows only**: Endpoint chat, file reads, memory reads, diagnostics

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).

---

<p align="center">
  Built with ❤️ for local-first AI autonomy
</p>
