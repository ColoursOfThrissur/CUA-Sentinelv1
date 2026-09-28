"""Task Execution Viewer - CLI tool to inspect task execution history."""

import sys
import io

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

DATA_DIR = Path(__file__).parent.parent.parent / "data"


def get_conn(db_name: str) -> sqlite3.Connection:
    conn = sqlite3.connect(DATA_DIR / f"{db_name}.sqlite")
    conn.row_factory = sqlite3.Row
    return conn


def list_recent_tasks(limit: int = 5) -> list[dict]:
    """List recent tasks with basic info."""
    conn = get_conn("operational")
    cur = conn.execute(
        """
        SELECT task_id, title, workflow_type, status, priority, created_at, updated_at
        FROM tasks ORDER BY created_at DESC LIMIT ?
        """,
        (limit,),
    )
    tasks = [dict(r) for r in cur.fetchall()]
    conn.close()
    return tasks


def get_task_steps(task_id: str) -> list[dict]:
    """Get all steps for a task."""
    conn = get_conn("operational")
    cur = conn.execute(
        """
        SELECT step_id, step_order, step_type, status, model_id, 
               input_context, output_summary, created_at, started_at, finished_at
        FROM task_steps WHERE task_id = ? ORDER BY step_order ASC
        """,
        (task_id,),
    )
    steps = [dict(r) for r in cur.fetchall()]
    conn.close()
    return steps


def get_task_audit_logs(task_id: str) -> list[dict]:
    """Get audit logs for a task (LLM calls, tool calls, state changes)."""
    conn = get_conn("audit")
    cur = conn.execute(
        """
        SELECT log_id, action_type, who_actor, tool_name, 
               decision_summary, decision_factors, created_at
        FROM audit_logs WHERE task_id = ? ORDER BY log_sequence ASC
        """,
        (task_id,),
    )
    logs = [dict(r) for r in cur.fetchall()]
    conn.close()
    return logs


def get_llm_traces(task_id: str) -> list[dict]:
    """Get full LLM call traces for a task."""
    conn = get_conn("operational")
    try:
        cur = conn.execute(
            """
            SELECT trace_id, model_id, system_prompt, user_prompt, response,
                   tokens_in_est, tokens_out_est, temperature, duration_ms, error, created_at
            FROM llm_traces WHERE task_id = ? ORDER BY trace_id ASC
            """,
            (task_id,),
        )
        return [dict(r) for r in cur.fetchall()]
    except:
        return []  # Table may not exist yet
    finally:
        conn.close()


def format_json(data: Optional[str], max_len: int = 200) -> str:
    """Pretty format JSON string, truncated."""
    if not data:
        return "-"
    try:
        obj = json.loads(data) if isinstance(data, str) else data
        formatted = json.dumps(obj, indent=2)
        if len(formatted) > max_len:
            return formatted[:max_len] + "..."
        return formatted
    except:
        return str(data)[:max_len]


def find_task_id(partial_id: str) -> Optional[str]:
    """Find full task ID from partial match."""
    conn = get_conn("operational")
    cur = conn.execute(
        "SELECT task_id FROM tasks WHERE task_id LIKE ? ORDER BY created_at DESC LIMIT 1",
        (f"{partial_id}%",),
    )
    row = cur.fetchone()
    conn.close()
    return row["task_id"] if row else None


def print_task_detail(task_id: str, verbose: bool = False):
    """Print detailed execution trace for a task."""
    # Get task info
    conn = get_conn("operational")
    cur = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,))
    task = cur.fetchone()
    conn.close()

    if not task:
        print(f"Task not found: {task_id}")
        return

    print("\n" + "=" * 80)
    print(f"TASK: {task['title'] or task['task_id']}")
    print("=" * 80)
    print(f"  ID:       {task['task_id']}")
    print(f"  Type:     {task['workflow_type']}")
    print(f"  Status:   {task['status']}")
    print(f"  Priority: {task['priority']}")
    print(f"  Created:  {task['created_at']}")
    if task['error_message']:
        print(f"  Error:    {task['error_message'][:100]}")

    # Get steps
    steps = get_task_steps(task_id)
    if steps:
        print(f"\n--- STEPS ({len(steps)}) ---")
        for s in steps:
            status_icon = {"COMPLETED": "OK", "FAILED": "X", "RUNNING": "..", "PENDING": "--"}.get(s["status"], "?")
            print(f"\n  [{status_icon}] Step {s['step_order']}: {s['step_type']}")
            print(f"      Model: {s['model_id'] or '-'}")
            if s["output_summary"] and verbose:
                print(f"      Output: {format_json(s['output_summary'], 150)}")

    # Get audit logs
    logs = get_task_audit_logs(task_id)
    if logs:
        # Group by type
        llm_calls = [l for l in logs if l["action_type"] == "MODEL_GENERATED"]
        tool_calls = [l for l in logs if l["action_type"] == "TOOL_GATEWAY_DECISION"]
        state_changes = [l for l in logs if l["action_type"] not in ("MODEL_GENERATED", "TOOL_GATEWAY_DECISION")]

        if llm_calls:
            print(f"\n--- LLM CALLS ({len(llm_calls)}) ---")
            for i, l in enumerate(llm_calls[:10]):  # Show max 10
                factors = json.loads(l["decision_factors"]) if l["decision_factors"] else {}
                summary = json.loads(l["decision_summary"]) if l["decision_summary"] else {}
                model = factors.get("model_id") or summary.get("model_id", "?")
                tokens_in = summary.get("tokens_in_est", "?")
                tokens_out = summary.get("tokens_out_est", "?")
                print(f"  {i+1}. {model} | in:{tokens_in} out:{tokens_out} | {l['created_at'][:19]}")

        if tool_calls:
            print(f"\n--- TOOL CALLS ({len(tool_calls)}) ---")
            for i, l in enumerate(tool_calls[:15]):  # Show max 15
                summary = json.loads(l["decision_summary"]) if l["decision_summary"] else {}
                decision = summary.get("decision", "?")
                icon = "OK" if decision == "ALLOWED" else "X"
                tool = l["tool_name"] or "?"
                print(f"  {i+1}. [{icon}] {tool}")
                if verbose and l["decision_factors"]:
                    factors = json.loads(l["decision_factors"])
                    if factors.get("input"):
                        print(f"       Input: {format_json(factors['input'], 100)}")
                    if factors.get("output"):
                        print(f"       Output: {format_json(factors['output'], 100)}")

        if state_changes:
            print(f"\n--- STATE CHANGES ({len(state_changes)}) ---")
            for l in state_changes[:10]:
                print(f"  - {l['action_type']} by {l['who_actor']} @ {l['created_at'][:19]}")

    # Get full LLM traces (if available)
    traces = get_llm_traces(task_id)
    if traces:
        print(f"\n--- LLM TRACES ({len(traces)}) ---")
        for i, t in enumerate(traces):
            print(f"\n  [{i+1}] {t['model_id']} | {t['tokens_in_est']}tok in -> {t['tokens_out_est']}tok out | {t['duration_ms']}ms")
            if t['error']:
                print(f"      ERROR: {t['error']}")
            if verbose:
                if t['system_prompt']:
                    print(f"      SYSTEM: {t['system_prompt'][:200]}{'...' if len(t['system_prompt'] or '') > 200 else ''}")
                print(f"      PROMPT: {t['user_prompt'][:300]}{'...' if len(t['user_prompt'] or '') > 300 else ''}")
                if t['response']:
                    print(f"      RESPONSE: {t['response'][:500]}{'...' if len(t['response'] or '') > 500 else ''}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Task Execution Viewer")
    parser.add_argument("--list", "-l", type=int, nargs="?", const=5, help="List recent tasks (default: 5)")
    parser.add_argument("--task", "-t", type=str, help="Show detail for specific task ID")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show full input/output")
    parser.add_argument("--latest", "-L", type=int, nargs="?", const=1, help="Show detail for N latest tasks")
    args = parser.parse_args()

    if args.list:
        tasks = list_recent_tasks(args.list)
        print(f"\n{'='*80}")
        print(f"RECENT TASKS (last {len(tasks)})")
        print(f"{'='*80}")
        for t in tasks:
            status_icon = {"COMPLETED": "OK", "FAILED": "X", "RUNNING": "..", "QUEUED": "--"}.get(t["status"], "?")
            title = (t["title"] or "Untitled")[:40]
            print(f"  [{status_icon}] {t['task_id'][:12]}  {t['workflow_type']:12} {title}")
        print()

    elif args.task:
        full_id = find_task_id(args.task)
        if full_id:
            print_task_detail(full_id, verbose=args.verbose)
        else:
            print(f"Task not found: {args.task}")

    elif args.latest:
        tasks = list_recent_tasks(args.latest)
        for t in tasks:
            print_task_detail(t["task_id"], verbose=args.verbose)

    else:
        # Default: show latest 5 tasks with details
        tasks = list_recent_tasks(5)
        for t in tasks:
            print_task_detail(t["task_id"], verbose=args.verbose)


if __name__ == "__main__":
    main()
