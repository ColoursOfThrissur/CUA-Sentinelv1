# SENTINEL PILOT PROFILE - ADDENDUM TO SOLUTION RUNTIME ARCHITECTURE v2
**Date:** 19 September 2026  
**Companion to:** proposed_agentic_ai_system_v2.txt (referred to as "v2")  
**Status:** Implementation-oriented specification for CUA-Sentinel.

---

## 1. Scope, Non-Goals, Ground Rules

### Scope
Make Sentinel a real, working test of the v2 architecture, using the Personal Finance (multi-currency, live market intelligence) module as the pilot domain. Close safety and correctness gaps (G1–G8) first.

### Non-Goals (Pilot)
- No autonomous trading or order placement (read-and-display only).
- No A2A, no multi-tenant identity, no agent registry service.
- No graph database, no vector store as source of truth.
- No rewrite of code-refactor / verification path (already proposal-and-gate).
- No canary or shadow traffic (replay against golden set instead).

### Ground Rules
- **R1 Local-First:** Financial data, Gmail content, and screen captures stay on machine. Nothing sent to external LLMs.
- **R2 No Floats for Money:** Store integer minor units or Decimal strings with currency codes.
- **R3 Provenance & TTL:** Every fact states author, evidence, and validity window.
- **R4 External Content is Data:** Unstrusted input cannot grant permissions or issue instructions.
- **R5 Masking:** Logs and traces mask account numbers, PANs, email addresses.
- **R6 Simplicity:** A layer stays only if it beats the baseline.

---

## 2. Gap Register (Verified Findings)
- **G1**: Untrusted content can act as instructions (no sealed envelope, raw concatenation in `endpoint_agent.py`).
- **G2**: Tool calls do not all pass one checkpoint (direct calls to `link_manager`, `finance_tools`, `desktop_tool`).
- **G3**: Claims only partly traceable (missing agent identity, model ID, prompt hash, validity window).
- **G4**: Resumed tasks restart from beginning (`queue.py` resets to `QUEUED`, runs from step 0).
- **G5**: Nothing detects behavioral regression (no LLM golden benchmark tests).
- **G6**: Trace rows carry no version stamps (`model_id`, `prompt_hash`, `config_version`, `gateway_version`).
- **G7**: Token gate protects app from outsiders, but doesn't limit agent execution authority.
- **G8**: No typed state model for finance domain yet.

---

## 3. Order of Work (Section 9)
- **STEP 1 (S)**: Version stamps on audit rows (P0.3), plus failing injection and bypass tests (G1 & G2).
- **STEP 2 (M)**: Tool registry + gateway + migrate all direct calls (P0.1).
- **STEP 3 (M)**: Envelope + nonce + action restriction (P0.2).
- **STEP 4 (M)**: Checkpoint and resume, cooperative preemption (P0.4).
- **STEP 5 (M)**: Golden set (30 cases) + runner + baseline report (P1).
- **STEP 6 (L)**: state.db, ontology-lite, write gate, views (P2).
- **STEP 7 (M)**: Declarative profiles for LLM-dependent agents (P3).
- **STEP 8 (S)**: Result cache; hints only after review exists (P4).
- **STEP 9 (M)**: MCP wrapping, only if needed (P5).
