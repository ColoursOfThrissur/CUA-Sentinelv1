import uuid
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from dataclasses import dataclass

from db.connections import get_operational_db
from db.connections import get_knowledge_db
from core.state_manager import LeaseValidationError, StateManager, StateTransitionError, utc_now

logger = logging.getLogger(__name__)


@dataclass
class TaskClaimResult:
    task_id: str
    lease_id: str
    lease_generation: int
    workflow_type: str
    priority: int
    context_budget: int
    input_payload: dict


class TaskQueue:
    """
    BP01 is the only queue. No in-memory lists or Python Queue objects.
    All state lives in operational.sqlite. Safe to restart at any time.
    """

    def __init__(self, config: dict):
        self.worker_id = config["system"]["worker_id"]
        self.lease_duration_sec = config["scheduler"]["lease_duration_sec"]
        self.aging_boost_per_hour = config["scheduler"]["aging_boost_per_hour"]
        self.state = StateManager()

    def _effective_priority(self, base_priority: int, created_at_iso: str) -> float:
        """
        Lower float = higher urgency.
        P0 starts at 0.0, P2 starts at 2.0.
        Every hour of waiting reduces the float so a starved P2 eventually
        beats a fresh P0.
        """
        created_at = datetime.fromisoformat(created_at_iso.replace("Z", "+00:00"))
        wait_hours = (datetime.now(timezone.utc) - created_at).total_seconds() / 3600
        return float(base_priority) - (wait_hours * self.aging_boost_per_hour)

    def enqueue(
        self,
        workflow_type: str,
        title: str,
        input_payload: dict,
        priority: int = 2,
        context_budget: int = 8192,
        description: str = None,
        parent_task_id: str = None,
    ) -> str:
        task_id = str(uuid.uuid4())
        now = utc_now()
        conn = get_operational_db()
        try:
            conn.execute(
                """
                INSERT INTO tasks (
                    task_id, parent_task_id, workflow_type, title, description,
                    priority, context_budget, input_payload, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'QUEUED', ?, ?)
                """,
                (
                    task_id, parent_task_id, workflow_type, title, description,
                    priority, context_budget, json.dumps(input_payload), now, now,
                ),
            )
            conn.commit()
            self._create_task_graph_root(task_id, title, description or workflow_type)
            logger.info(f"Enqueued task {task_id} type={workflow_type} priority={priority}")
            return task_id
        finally:
            conn.close()

    def _create_task_graph_root(self, task_id: str, title: str, objective: str) -> None:
        conn = get_knowledge_db()
        try:
            conn.execute(
                """
                INSERT OR IGNORE INTO task_graph_nodes (
                    node_id, task_id, node_type, title, objective
                ) VALUES (?, ?, 'GOAL', ?, ?)
                """,
                (task_id, task_id, title, objective),
            )
            conn.commit()
        finally:
            conn.close()

    def claim_next_task(self, worker_capabilities: list, allowed_workflows: Optional[list] = None) -> Optional[TaskClaimResult]:
        conn = get_operational_db()
        try:
            query = """
                SELECT t.task_id, t.priority, t.created_at, t.workflow_type,
                       t.requested_capabilities, t.context_budget, t.input_payload
                FROM tasks t
                LEFT JOIN task_leases tl ON t.task_id = tl.task_id
                WHERE t.status = 'QUEUED' AND tl.task_id IS NULL
            """
            params = []
            if allowed_workflows:
                placeholders = ",".join(["?"] * len(allowed_workflows))
                query += f" AND t.workflow_type IN ({placeholders})"
                params.extend(allowed_workflows)

            rows = conn.execute(query, params).fetchall()

            if not rows:
                return None

            candidates = []
            for row in rows:
                req_caps = json.loads(row["requested_capabilities"]) if row["requested_capabilities"] else []
                if all(cap in worker_capabilities for cap in req_caps):
                    eff = self._effective_priority(row["priority"], row["created_at"])
                    candidates.append((eff, dict(row)))

            if not candidates:
                return None

            candidates.sort(key=lambda x: x[0])
            return self._atomic_claim(conn, candidates[0][1])
        finally:
            conn.close()

    def _atomic_claim(self, conn, task: dict) -> Optional[TaskClaimResult]:
        lease_id = str(uuid.uuid4())
        now = utc_now()
        expires_at = (
            datetime.now(timezone.utc) + timedelta(seconds=self.lease_duration_sec)
        ).isoformat()

        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT status FROM tasks WHERE task_id = ?", (task["task_id"],)
            ).fetchone()

            if not row or row["status"] != "QUEUED":
                conn.execute("ROLLBACK")
                return None

            conn.execute(
                "UPDATE tasks SET status = 'RUNNING', updated_at = ? WHERE task_id = ?",
                (now, task["task_id"]),
            )
            conn.execute(
                """
                INSERT INTO task_leases
                    (lease_id, task_id, owner_worker_id, lease_generation, expires_at)
                VALUES (?, ?, ?, 1, ?)
                """,
                (lease_id, task["task_id"], self.worker_id, expires_at),
            )
            conn.execute("COMMIT")
            self.state.audit(
                action_type="TASK_CLAIMED",
                who_actor=self.worker_id,
                task_id=task["task_id"],
                result={"lease_id": lease_id, "lease_generation": 1},
            )
            logger.info(f"Claimed task {task['task_id']} lease={lease_id}")

            return TaskClaimResult(
                task_id=task["task_id"],
                lease_id=lease_id,
                lease_generation=1,
                workflow_type=task["workflow_type"],
                priority=task["priority"],
                context_budget=task["context_budget"] or 8192,
                input_payload=json.loads(task["input_payload"]) if task["input_payload"] else {},
            )
        except Exception as e:
            conn.execute("ROLLBACK")
            logger.error(f"Atomic claim failed for {task['task_id']}: {e}")
            return None

    def heartbeat_lease(self, task_id: str, lease_id: str, lease_generation: int) -> bool:
        now = utc_now()
        expires_at = (
            datetime.now(timezone.utc) + timedelta(seconds=self.lease_duration_sec)
        ).isoformat()
        conn = get_operational_db()
        try:
            self.state.validate_task_lease(conn, task_id, lease_id, lease_generation)
            result = conn.execute(
                """
                UPDATE task_leases SET heartbeat = ?, expires_at = ?
                WHERE task_id = ? AND lease_id = ? AND lease_generation = ?
                """,
                (now, expires_at, task_id, lease_id, lease_generation),
            )
            conn.commit()
            return result.rowcount > 0
        except LeaseValidationError:
            return False
        finally:
            conn.close()

    def release_task(
        self,
        task_id: str,
        lease_id: str,
        status: str,
        result_payload: dict = None,
        error: str = None,
    ) -> None:
        try:
            self.state.transition_task(
                task_id=task_id,
                new_status=status,
                lease_id=lease_id,
                lease_generation=self._get_lease_generation(task_id, lease_id),
                result_payload=result_payload,
                error_message=error,
                release_lease=True,
                actor=self.worker_id,
            )
            logger.info(f"Released task {task_id} status={status}")
        except Exception as e:
            logger.error(f"Failed to release task {task_id}: {e}")

    def _get_lease_generation(self, task_id: str, lease_id: str) -> int:
        conn = get_operational_db()
        try:
            row = conn.execute(
                "SELECT lease_generation FROM task_leases WHERE task_id = ? AND lease_id = ?",
                (task_id, lease_id),
            ).fetchone()
            if not row:
                raise LeaseValidationError(f"No lease found for task {task_id}")
            return int(row["lease_generation"])
        finally:
            conn.close()

    def preempt_task(self, task_id: str, lease_id: str) -> bool:
        """Pause a running task so a higher priority task can run."""
        try:
            self.state.transition_task(
                task_id=task_id,
                new_status="PREEMPTED",
                lease_id=lease_id,
                lease_generation=self._get_lease_generation(task_id, lease_id),
                release_lease=True,
                actor=self.worker_id,
            )
            logger.info(f"Preempted task {task_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to preempt task {task_id}: {e}")
            return False

    def expire_stale_leases(self) -> int:
        """Called by watchdog. Returns tasks back to QUEUED if lease expired."""
        now = utc_now()
        now_dt = datetime.now(timezone.utc)
        conn = get_operational_db()
        try:
            leases = conn.execute("SELECT task_id, lease_id, expires_at FROM task_leases").fetchall()

            count = 0
            for row in leases:
                try:
                    exp_dt = datetime.fromisoformat(row["expires_at"].replace("Z", "+00:00"))
                except Exception:
                    exp_dt = datetime.min.replace(tzinfo=timezone.utc)

                if now_dt >= exp_dt:
                    try:
                        conn.execute("BEGIN IMMEDIATE")
                        conn.execute(
                            """
                            UPDATE tasks
                            SET status = 'QUEUED', updated_at = ?
                            WHERE task_id = ? AND status IN ('RUNNING', 'PREEMPTED')
                            """,
                            (now, row["task_id"]),
                        )
                        conn.execute("DELETE FROM task_leases WHERE lease_id = ?", (row["lease_id"],))
                        conn.execute("COMMIT")
                        self.state.audit(
                            action_type="LEASE_EXPIRED_REQUEUED",
                            who_actor="Watchdog",
                            task_id=row["task_id"],
                            result={"lease_id": row["lease_id"]},
                        )
                        count += 1
                        logger.warning(f"Expired stale lease for task {row['task_id']}")
                    except Exception as e:
                        conn.execute("ROLLBACK")
                        logger.error(f"Failed to expire lease for {row['task_id']}: {e}")

            return count
        finally:
            conn.close()

    def recover_interrupted_tasks(self) -> int:
        """
        Called on backend startup.
        Resets any tasks left in 'RUNNING' status from a previous boot session back to 'QUEUED'.
        """
        now = utc_now()
        conn = get_operational_db()
        try:
            running_tasks = conn.execute(
                "SELECT task_id FROM tasks WHERE status = 'RUNNING'"
            ).fetchall()
            if not running_tasks:
                return 0

            count = 0
            for row in running_tasks:
                tid = row["task_id"]
                conn.execute(
                    "UPDATE tasks SET status = 'QUEUED', updated_at = ? WHERE task_id = ?",
                    (now, tid),
                )
                conn.execute("DELETE FROM task_leases WHERE task_id = ?", (tid,))
                count += 1
                logger.info(f"Recovered interrupted task {tid} -> reset status to QUEUED")

            conn.commit()
            return count
        except Exception as err:
            logger.error(f"Error during interrupted task recovery: {err}")
            return 0
        finally:
            conn.close()
