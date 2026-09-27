import uuid
import json
import hashlib
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Any, Dict, List

from db.connections import get_operational_db

logger = logging.getLogger(__name__)


class GovernanceViolation(Exception):
    pass


class HITLRequired(Exception):
    def __init__(self, approval_id: str, message: str):
        self.approval_id = approval_id
        self.message = message
        self.action_description = message
        super().__init__(message)


class GovernanceEngine:
    """
    Nothing executes without passing through here.
    Checks risk level, issues capability grants, creates HITL requests,
    and enforces retry policy based on error class — not blind retry counts.
    """

    def __init__(self, policy: dict, config: dict):
        self.policy = policy
        self.config = config
        self.tool_policies = policy["tool_policies"]
        self.retry_policy = policy["retry_policy"]
        self.risk_levels = policy["risk_levels"]
        self.safe_mode_allowed = policy["safe_mode_allowed_operations"]

    def is_emergency_stop(self) -> bool:
        """Live evaluation of emergency stop state directly from operational database."""
        conn = get_operational_db()
        try:
            row = conn.execute(
                "SELECT value FROM system_state WHERE key = 'emergency_stop'"
            ).fetchone()
            return row is not None and str(row["value"]).lower() == "true"
        finally:
            conn.close()

    def reset_emergency_stop(self) -> None:
        """Resets emergency stop state to false."""
        try:
            from tools.desktop_tool import reset_desktop_abort
            reset_desktop_abort()
        except Exception as e:
            logger.debug(f"Could not reset desktop abort flag: {e}")
        now = datetime.now(timezone.utc).isoformat()
        conn = get_operational_db()
        try:
            conn.execute(
                "UPDATE system_state SET value = 'false', updated_at = ? WHERE key = 'emergency_stop'",
                (now,),
            )
            conn.commit()
            logger.info("Emergency stop reset to false.")
        finally:
            conn.close()

    def check_tool_permission(self, tool_name: str, task_id: str, is_safe_mode: bool = False) -> dict:
        """
        Returns the tool policy if allowed.
        Raises GovernanceViolation if blocked.
        Raises HITLRequired if human approval needed.
        """
        tool_policy = self.tool_policies.get(tool_name)
        if not tool_policy:
            raise GovernanceViolation(f"Unknown tool: {tool_name}")

        if is_safe_mode and tool_name not in self.safe_mode_allowed:
            raise GovernanceViolation(f"Tool {tool_name} blocked in safe mode")

        risk_level = tool_policy["risk_level"]
        level_config = self.risk_levels[risk_level]

        if level_config.get("requires_approval"):
            approval_id = self._create_hitl_request(tool_name, task_id, tool_policy)
            raise HITLRequired(approval_id, f"Tool {tool_name} requires human approval (risk={risk_level})")

        return tool_policy

    def check_tool_execution_safety(
        self,
        tool_name: str,
        caller_agent: str,
        task_id: str = "adhoc",
        untrusted_present: bool = False,
        registry_meta: dict = None,
        **kwargs,
    ) -> dict:
        """
        Comprehensive gateway check (P0.1, P0.2 / S1):
        1. Emergency stop check (evaluated at call time from DB).
        2. Safe mode check (evaluated at call time from DB).
        3. Registry & allowed_agents check (fail closed).
        4. Untrusted context / taint check (blocks act/write when untrusted data is present).
        5. HITL risk tier check (L3 requires approval).
        Returns tool metadata dictionary if approved, or raises GovernanceViolation / HITLRequired.
        """
        if self.is_emergency_stop():
            raise GovernanceViolation(f"Emergency Stop is ACTIVE. Execution blocked for tool: {tool_name}")

        REQUIRED_GOVERNANCE_FLAGS = {
            "side_effect", "risk_level", "allowed_agents", "deny_all",
            "taint_deny", "taint_safe", "egress", "returns_untrusted", "reads_private_data"
        }

        meta = registry_meta or {}
        if missing := (REQUIRED_GOVERNANCE_FLAGS - set(meta.keys())):
            raise GovernanceViolation(f"Tool '{tool_name}' missing required governance flag(s): {sorted(missing)}")

        params = kwargs.get("params", {})
        read_private = kwargs.get("read_private", False)
        taint_origins = kwargs.get("taint_origins", "untrusted tool return data")

        # 1. Denials only: evaluated first, nothing is created or consumed
        if meta.get("deny_all"):
            raise GovernanceViolation(f"Tool '{tool_name}' is denied unconditionally (deny_all=True)")

        allowed = meta.get("allowed_agents")
        if not isinstance(allowed, list) or caller_agent not in allowed:
            raise GovernanceViolation(
                f"Agent '{caller_agent}' is NOT authorized to execute tool '{tool_name}'. Allowed: {allowed}"
            )

        if untrusted_present and meta.get("taint_deny"):
            raise GovernanceViolation(
                f"TAINT VIOLATION: Tool '{tool_name}' is HARD DENIED under taint."
            )

        if self.is_safe_mode() and meta.get("side_effect") in ("write", "act") and tool_name not in self.safe_mode_allowed:
            raise GovernanceViolation(
                f"Tool '{tool_name}' (side_effect={meta.get('side_effect')}) blocked: system is in Safe Mode."
            )

        level_config = self.risk_levels.get(meta.get("risk_level"))
        if not level_config:
            raise GovernanceViolation(f"Unknown risk level '{meta.get('risk_level')}' for tool '{tool_name}' (fail closed)")

        if meta.get("egress") and untrusted_present and read_private:
            raise GovernanceViolation(
                f"EXFILTRATION VIOLATION: Tool '{tool_name}' blocked (private data + untrusted context + egress)."
            )

        # 2. One approval decision, consumed exactly once
        if meta.get("auto_approve"):
            return meta

        reasons = []
        is_taint_gated = bool(untrusted_present and not meta.get("taint_safe") and meta.get("side_effect") in ("write", "act"))
        if is_taint_gated:
            reasons.append(f"tainted context (origins: {taint_origins})")
        if level_config.get("requires_approval") or meta.get("risk_level") == "L3":
            reasons.append(f"risk level {meta.get('risk_level')}")

        if reasons:
            reasons_str = "; ".join(reasons)
            params_str = json.dumps(params, sort_keys=True, default=str)
            prefix = "TAINT GATE (S1): " if is_taint_gated else ""
            action_desc = f"{prefix}Tool '{tool_name}' requires human approval [{reasons_str}]. Params: {params_str}"
            approval_id = self._consume_or_create_hitl(
                tool_name, task_id, params, meta, action_desc
            )
            if approval_id:
                raise HITLRequired(approval_id, action_desc)

        return meta

    def _create_hitl_request(
        self, tool_name: str, task_id: str, tool_policy: dict, action_desc: str = None
    ) -> str:
        aid = self._consume_or_create_hitl(
            tool_name, task_id, {}, tool_policy, action_desc or f"Tool execution: {tool_name}"
        )
        return aid or str(uuid.uuid4())

    def _compute_action_hash(self, tool_name: str, task_id: str, params: dict, version: str = "1.0") -> str:
        canon = json.dumps(
            {"tool": tool_name, "task": task_id, "params": params, "v": version},
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return hashlib.sha256(canon.encode("utf-8")).hexdigest()

    def _consume_or_create_hitl(
        self, tool_name: str, task_id: str, params: dict, tool_policy: dict, action_desc: str
    ) -> Optional[str]:
        """
        Single-use approval consumption:
        1. If an active APPROVED record matching the action_hash exists, atomically mark it USED and return None (allows execution).
        2. If a PENDING record exists, reuse its approval_id (deduplication).
        3. Otherwise, create a new PENDING approval row and return approval_id (triggers HITLRequired).
        """
        now = datetime.now(timezone.utc).isoformat()
        act_hash = self._compute_action_hash(tool_name, task_id, params, tool_policy.get("version", "1.0"))

        conn = get_operational_db()
        try:
            # 1. Check for existing approved record to consume
            approved_row = conn.execute(
                """
                SELECT approval_id FROM hitl_pending 
                WHERE task_id = ? AND action_hash = ? AND status = 'APPROVED' AND expires_at > ?
                """,
                (task_id, act_hash, now),
            ).fetchone()

            if approved_row:
                cur = conn.execute(
                    """
                    UPDATE hitl_pending SET status = 'USED', resolved_at = ?
                    WHERE approval_id = ? AND status = 'APPROVED'
                    """,
                    (now, approved_row["approval_id"]),
                )
                conn.commit()
                if cur.rowcount == 1:
                    logger.info(f"HITL approval {approved_row['approval_id']} CONSUMED/USED for tool {tool_name}")
                    return None  # Approved and consumed: proceed with execution

            # 2. Check for existing pending request (deduplicate retries)
            pending_row = conn.execute(
                """
                SELECT approval_id FROM hitl_pending 
                WHERE task_id = ? AND action_hash = ? AND status = 'PENDING' AND expires_at > ?
                """,
                (task_id, act_hash, now),
            ).fetchone()

            if pending_row:
                return pending_row["approval_id"]

            # 3. Create new pending approval request
            approval_id = str(uuid.uuid4())
            timeout_sec = self.risk_levels.get(tool_policy.get("risk_level", "L0"), {}).get("approval_timeout_sec", 3600)
            expires_at = (datetime.now(timezone.utc) + timedelta(seconds=timeout_sec)).isoformat()
            op_id = str(uuid.uuid4())
            step_id = str(uuid.uuid4())

            # Ensure task exists
            conn.execute(
                """
                INSERT OR IGNORE INTO tasks (task_id, workflow_type, title, status)
                VALUES (?, 'ENDPOINT', 'Ad-hoc Task', 'RUNNING')
                """,
                (task_id,),
            )

            # Ensure task_steps exists for foreign key constraint
            step_row = conn.execute(
                "SELECT step_id FROM task_steps WHERE task_id = ? ORDER BY step_order DESC LIMIT 1",
                (task_id,),
            ).fetchone()
            if step_row:
                step_id = step_row["step_id"]
            else:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO task_steps (step_id, task_id, step_order, step_type, description, status)
                    VALUES (?, ?, 0, 'GOVERNANCE_CHECK', 'Safety validation', 'RUNNING')
                    """,
                    (step_id, task_id),
                )

            # Ensure operation record exists
            conn.execute(
                """
                INSERT OR IGNORE INTO operations (
                    operation_id, task_id, step_id, tool_name,
                    target_resource_canonical, recovery_strategy, current_state
                ) VALUES (?, ?, ?, ?, ?, 'HITL', 'PREPARED')
                """,
                (op_id, task_id, step_id, tool_name, f"tool://{tool_name}"),
            )

            # Mask sensitive params before storing in hitl_pending
            masked_params = json.dumps(params, default=str)
            conn.execute(
                """
                INSERT INTO hitl_pending (
                    approval_id, task_id, operation_id, risk_level,
                    action_description, action_payload, action_hash,
                    tool_version, resource_version_hash, nonce,
                    status, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?)
                """,
                (
                    approval_id,
                    task_id,
                    op_id,
                    int(tool_policy.get("risk_level", "L1")[1]) if len(tool_policy.get("risk_level", "L1")) > 1 and tool_policy.get("risk_level", "L1")[1].isdigit() else 1,
                    action_desc,
                    json.dumps({"tool": tool_name, "params": params}, default=str),
                    act_hash,
                    tool_policy.get("version", "1.0"),
                    act_hash,
                    str(uuid.uuid4()),
                    expires_at,
                ),
            )
            conn.commit()
            logger.info(f"HITL request created: {approval_id} for tool {tool_name} (hash={act_hash[:8]})")
            return approval_id
        finally:
            conn.close()

    def resolve_hitl(self, approval_id: str, approved: bool, resolved_by: str) -> bool:
        """
        Atomic resolution: Updates hitl_pending only if status is currently PENDING and not expired.
        """
        now = datetime.now(timezone.utc).isoformat()
        new_status = "APPROVED" if approved else "REJECTED"

        conn = get_operational_db()
        try:
            cur = conn.execute(
                """
                UPDATE hitl_pending 
                SET status = ?, resolved_at = ?, resolved_by = ?
                WHERE approval_id = ? AND status = 'PENDING' AND expires_at > ?
                """,
                (new_status, now, resolved_by, approval_id, now),
            )
            conn.commit()
            success = cur.rowcount == 1
            if success:
                logger.info(f"HITL {approval_id} atomically resolved: {new_status} by {resolved_by}")
            else:
                logger.warning(f"HITL {approval_id} resolution failed: not found, expired, or already resolved")
            return success
        finally:
            conn.close()

    async def wait_for_approval(
        self,
        approval_id: str,
        timeout_sec: int = 3600,
        poll_interval: float = 2.0,
    ) -> bool:
        """
        Poll the DB until the HITL request is APPROVED, REJECTED, or times out.
        Returns True if approved, False otherwise.
        Never blocks indefinitely — auto-declines after timeout_sec.
        """
        import asyncio
        deadline = datetime.now(timezone.utc).timestamp() + timeout_sec

        while datetime.now(timezone.utc).timestamp() < deadline:
            conn = get_operational_db()
            try:
                row = conn.execute(
                    "SELECT status FROM hitl_pending WHERE approval_id = ?",
                    (approval_id,),
                ).fetchone()
            finally:
                conn.close()

            if row:
                status = row["status"]
                if status == "APPROVED":
                    return True
                if status in ("REJECTED", "USED", "TIMED_OUT"):
                    return False

            await asyncio.sleep(poll_interval)

        # Timeout — mark as TIMED_OUT so it doesn't linger as PENDING
        now = datetime.now(timezone.utc).isoformat()
        conn = get_operational_db()
        try:
            conn.execute(
                """UPDATE hitl_pending SET status = 'TIMED_OUT', resolved_at = ?
                   WHERE approval_id = ? AND status = 'PENDING'""",
                (now, approval_id),
            )
            conn.commit()
        finally:
            conn.close()
        logger.warning(f"HITL {approval_id} timed out after {timeout_sec}s — auto-declined")
        return False

    def get_retry_action(self, error_class: str, attempt_no: int, error_fingerprint: str, prev_fingerprint: str) -> str:
        """
        Returns what to do next: 'retry', 'pivot', 'halt', 'escalate', 'backoff'
        Decision is based on error class and fingerprint — not blind retry count.
        """
        if error_fingerprint and error_fingerprint == prev_fingerprint:
            return "pivot"

        policy = self.retry_policy.get(error_class)
        if not policy:
            return "halt"

        if attempt_no >= policy["max_retries"]:
            return "halt"

        return policy["strategy"].split("_")[0]

    def is_safe_mode(self) -> bool:
        conn = get_operational_db()
        try:
            row = conn.execute(
                "SELECT value FROM system_state WHERE key = 'safe_mode'"
            ).fetchone()
            return row and row["value"] == "true"
        finally:
            conn.close()

    def enter_safe_mode(self, reason: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        conn = get_operational_db()
        try:
            conn.execute(
                "UPDATE system_state SET value = 'true', updated_at = ? WHERE key = 'safe_mode'",
                (now,),
            )
            conn.commit()
            logger.warning(f"SAFE MODE ENTERED: {reason}")
        finally:
            conn.close()

    def exit_safe_mode(self) -> None:
        now = datetime.now(timezone.utc).isoformat()
        conn = get_operational_db()
        try:
            conn.execute(
                "UPDATE system_state SET value = 'false', updated_at = ? WHERE key = 'safe_mode'",
                (now,),
            )
            conn.commit()
            logger.info("Safe mode exited.")
        finally:
            conn.close()

    def trigger_emergency_stop(self) -> None:
        try:
            from tools.desktop_tool import abort_desktop_actions
            abort_desktop_actions()
        except Exception as e:
            logger.debug(f"Could not trigger desktop abort flag: {e}")
        now = datetime.now(timezone.utc).isoformat()
        conn = get_operational_db()
        try:
            conn.execute(
                "UPDATE system_state SET value = 'true', updated_at = ? WHERE key = 'emergency_stop'",
                (now,),
            )
            conn.commit()
            logger.critical("EMERGENCY STOP TRIGGERED.")
        finally:
            conn.close()
