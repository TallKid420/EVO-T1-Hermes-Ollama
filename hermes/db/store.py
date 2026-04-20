import json
from datetime import datetime
from typing import Optional, Dict, Any, List

from hermes.db.conn import connect
from hermes.db.models import Event, Task, Action


VALID_TASK_STATUSES = {"queued", "running", "done", "failed", "blocked"}


def _now() -> str:
    return datetime.utcnow().isoformat()


# -------- Events --------

def add_event(
    severity: str,
    source: str,
    type_: str,
    message: str,
    payload: Dict[str, Any],
) -> int:
    conn = connect()
    try:
        cur = conn.execute(
            """
            INSERT INTO events(created_at, severity, source, type, message, payload_json, acknowledged_at)
            VALUES(?, ?, ?, ?, ?, ?, NULL)
            """,
            (_now(), severity, source, type_, message, json.dumps(payload, separators=(",", ":"))),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def list_events(limit: int = 50, unacked_only: bool = False) -> List[Event]:
    conn = connect()
    try:
        if unacked_only:
            rows = conn.execute(
                """
                SELECT * FROM events
                WHERE acknowledged_at IS NULL
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM events ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()

        out: List[Event] = []
        for r in rows:
            out.append(
                Event(
                    id=r["id"],
                    created_at=r["created_at"],
                    severity=r["severity"],
                    source=r["source"],
                    type=r["type"],
                    message=r["message"],
                    payload=json.loads(r["payload_json"]),
                    acknowledged_at=r["acknowledged_at"],
                )
            )
        return out
    finally:
        conn.close()


# -------- Tasks --------

def create_task(
    status: str,
    priority: int,
    type_: str,
    title: str,
    payload: Dict[str, Any],
    event_id: Optional[int] = None,
    requires_approval: bool = False,
) -> int:
    if status not in VALID_TASK_STATUSES:
        raise ValueError(f"Invalid task status: {status}")

    conn = connect()
    try:
        cur = conn.execute(
            """
            INSERT INTO tasks(
              created_at, updated_at, status, priority, type, title,
              payload_json, result_json, event_id, requires_approval, approved_at, blocked_reason, attempts
            )
            VALUES(?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, NULL, NULL, 0)
            """,
            (
                _now(),
                _now(),
                status,
                priority,
                type_,
                title,
                json.dumps(payload, separators=(",", ":")),
                event_id,
                1 if requires_approval else 0,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def list_tasks(limit: int = 50, status: Optional[str] = None) -> List[Task]:
    conn = connect()
    try:
        if status:
            rows = conn.execute(
                """
                SELECT * FROM tasks
                WHERE status = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (status, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM tasks ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()

        out: List[Task] = []
        for r in rows:
            out.append(
                Task(
                    id=r["id"],
                    created_at=r["created_at"],
                    updated_at=r["updated_at"],
                    status=r["status"],
                    priority=r["priority"],
                    type=r["type"],
                    title=r["title"],
                    payload=json.loads(r["payload_json"]),
                    result=json.loads(r["result_json"]) if r["result_json"] else None,
                    event_id=r["event_id"],
                    requires_approval=bool(r["requires_approval"]),
                    approved_at=r["approved_at"],
                    blocked_reason=r["blocked_reason"],
                    attempts=r["attempts"],
                )
            )
        return out
    finally:
        conn.close()


def get_task(task_id: int) -> Optional[Task]:
    conn = connect()
    try:
        r = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if not r:
            return None
        return Task(
            id=r["id"],
            created_at=r["created_at"],
            updated_at=r["updated_at"],
            status=r["status"],
            priority=r["priority"],
            type=r["type"],
            title=r["title"],
            payload=json.loads(r["payload_json"]),
            result=json.loads(r["result_json"]) if r["result_json"] else None,
            event_id=r["event_id"],
            requires_approval=bool(r["requires_approval"]),
            approved_at=r["approved_at"],
            blocked_reason=r["blocked_reason"],
            attempts=r["attempts"],
        )
    finally:
        conn.close()


def update_task_status(task_id: int, status: str, blocked_reason: Optional[str] = None):
    if status not in VALID_TASK_STATUSES:
        raise ValueError(f"Invalid task status: {status}")

    conn = connect()
    try:
        conn.execute(
            """
            UPDATE tasks
            SET status = ?, updated_at = ?, blocked_reason = ?
            WHERE id = ?
            """,
            (status, _now(), blocked_reason, task_id),
        )
        conn.commit()
    finally:
        conn.close()


def increment_task_attempts(task_id: int):
    conn = connect()
    try:
        conn.execute(
            "UPDATE tasks SET attempts = attempts + 1, updated_at = ? WHERE id = ?",
            (_now(), task_id),
        )
        conn.commit()
    finally:
        conn.close()


def set_task_result(task_id: int, result: Dict[str, Any]):
    conn = connect()
    try:
        conn.execute(
            """
            UPDATE tasks
            SET result_json = ?, updated_at = ?
            WHERE id = ?
            """,
            (json.dumps(result, separators=(",", ":")), _now(), task_id),
        )
        conn.commit()
    finally:
        conn.close()


def approve_task(task_id: int):
    conn = connect()
    try:
        conn.execute(
            """
            UPDATE tasks
            SET status = 'queued', approved_at = ?, blocked_reason = NULL
            WHERE id = ? AND status = 'blocked'
            """,
            (_now(), task_id),
        )
        conn.commit()
    finally:
        conn.close()


def claim_next_queued_task() -> Optional[Task]:
    """Atomically claim the next queued task and mark it running."""
    conn = connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            """
            SELECT id
            FROM tasks
            WHERE status = 'queued'
            ORDER BY priority DESC, id ASC
            LIMIT 1
            """
        ).fetchone()

        if row is None:
            conn.commit()
            return None

        task_id = int(row["id"])
        cur = conn.execute(
            """
            UPDATE tasks
            SET status = 'running',
                attempts = attempts + 1,
                updated_at = ?
            WHERE id = ? AND status = 'queued'
            """,
            (_now(), task_id),
        )
        if cur.rowcount != 1:
            conn.commit()
            return None

        claimed = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        conn.commit()

        if claimed is None:
            return None

        return Task(
            id=claimed["id"],
            created_at=claimed["created_at"],
            updated_at=claimed["updated_at"],
            status=claimed["status"],
            priority=claimed["priority"],
            type=claimed["type"],
            title=claimed["title"],
            payload=json.loads(claimed["payload_json"]),
            result=json.loads(claimed["result_json"]) if claimed["result_json"] else None,
            event_id=claimed["event_id"],
            requires_approval=bool(claimed["requires_approval"]),
            approved_at=claimed["approved_at"],
            blocked_reason=claimed["blocked_reason"],
            attempts=claimed["attempts"],
        )
    finally:
        conn.close()

# -------- Actions (Audit Log) --------

def add_action(
    task_id: Optional[int],
    tool: str,
    action: str,
    input_: Dict[str, Any],
    output: Optional[Dict[str, Any]],
    success: bool,
    duration_ms: Optional[int] = None,
    error: Optional[str] = None,
) -> int:
    conn = connect()
    try:
        cur = conn.execute(
            """
            INSERT INTO actions(created_at, task_id, tool, action, input_json, output_json, success, duration_ms, error)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _now(),
                task_id,
                tool,
                action,
                json.dumps(input_, separators=(",", ":")),
                json.dumps(output, separators=(",", ":")) if output is not None else None,
                1 if success else 0,
                duration_ms,
                error,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def list_actions(task_id: Optional[int] = None, limit: int = 100) -> List[Action]:
    conn = connect()
    try:
        if task_id is not None:
            rows = conn.execute(
                """
                SELECT * FROM actions
                WHERE task_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (task_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM actions ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()

        out: List[Action] = []
        for r in rows:
            out.append(
                Action(
                    id=r["id"],
                    created_at=r["created_at"],
                    task_id=r["task_id"],
                    tool=r["tool"],
                    action=r["action"],
                    input=json.loads(r["input_json"]),
                    output=json.loads(r["output_json"]) if r["output_json"] else None,
                    success=bool(r["success"]),
                    duration_ms=r["duration_ms"],
                    error=r["error"],
                )
            )
        return out
    finally:
        conn.close()