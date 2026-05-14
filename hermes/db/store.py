"""
hermes/db/store.py
Database access layer for Hermes.
Provides functions to create, read, update, and delete tasks, events, and actions.
Uses SQLite for storage and handles JSON serialization of payloads and results.
"""

import json
from datetime import datetime
from typing import Optional, Dict, Any, List

from hermes.db.conn import connect
from hermes.db.models import Event, Task, Action


VALID_TASK_STATUSES = {
    "queued",
    "running",
    "done",
    "failed",
    "blocked",
    "denied",
}

MAILBOX_PENDING_STATUS = "pending"


def _now() -> str:
    return datetime.utcnow().isoformat()


def _table_columns(conn, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {r["name"] for r in rows}


def _task_from_row(r) -> Task:
    """Build Task model from row, tolerating optional/new columns."""
    base_kwargs = dict(
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

    # Add lineage fields only if present in row
    row_keys = set(r.keys())
    if "parent_agent" in row_keys:
        base_kwargs["parent_agent"] = r["parent_agent"]
    if "spawn_depth" in row_keys:
        base_kwargs["spawn_depth"] = 0 if r["spawn_depth"] is None else r["spawn_depth"]

    # Backward compatibility if Task model hasn't been extended yet
    try:
        return Task(**base_kwargs)
    except TypeError:
        base_kwargs.pop("parent_agent", None)
        base_kwargs.pop("spawn_depth", None)
        return Task(**base_kwargs)


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
    parent_agent: Optional[str] = None,
    spawn_depth: int = 0,
) -> int:
    if status not in VALID_TASK_STATUSES:
        raise ValueError(f"Invalid task status: {status}")

    conn = connect()
    try:
        task_cols = _table_columns(conn, "tasks")
        has_lineage = {"parent_agent", "spawn_depth"}.issubset(task_cols)

        if has_lineage:
            cur = conn.execute(
                """
                INSERT INTO tasks(
                  created_at, updated_at, status, priority, type, title,
                  payload_json, result_json, event_id, requires_approval, approved_at, blocked_reason, attempts,
                  parent_agent, spawn_depth
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, NULL, NULL, 0, ?, ?)
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
                    parent_agent,
                    spawn_depth,
                ),
            )
        else:
            # Backward-compatible insert for pre-lineage schema
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

        return [_task_from_row(r) for r in rows]
    finally:
        conn.close()


def get_task(task_id: int) -> Optional[Task]:
    conn = connect()
    try:
        r = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if not r:
            return None
        return _task_from_row(r)
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


def _update_task(query, params):
    conn = connect()
    try:
        with conn:
            cur = conn.execute(query, params)
            if cur.rowcount == 0:
                raise ValueError("Invalid task state or ID")
    finally:
        conn.close()


def approve_task(task_id: int):
    _update_task(
        """
        UPDATE tasks
        SET status = 'queued', approved_at = ?, blocked_reason = NULL
        WHERE id = ? AND status = 'blocked'
        """,
        (_now(), task_id),
    )


def deny_task(task_id: int, reason: Optional[str] = None):
    _update_task(
        """
        UPDATE tasks
        SET status = 'denied', blocked_reason = ?
        WHERE id = ? AND status = 'blocked'
        """,
        (reason, task_id),
    )


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

        return _task_from_row(claimed)
    finally:
        conn.close()


# -------- Agent Nodes --------

def register_agent_node(
    agent_id: str,
    parent_id: Optional[str],
    name: str,
    type_: str,
    depth: int,
    mailbox_id: str,
    status: str = "online",
    meta: Optional[Dict[str, Any]] = None,
) -> int:
    """
    Register or update an agent runtime node.
    Requires `agent_nodes` table with columns:
    (created_at, updated_at, agent_id, parent_id, name, type, depth, mailbox_id, status, meta_json)
    and a UNIQUE constraint on agent_id for upsert behavior.
    """
    conn = connect()
    try:
        now = _now()
        cur = conn.execute(
            """
            INSERT INTO agent_nodes(
                created_at, updated_at, agent_id, parent_id, name, type, depth, mailbox_id, status, meta_json
            )
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(agent_id) DO UPDATE SET
                updated_at = excluded.updated_at,
                parent_id = excluded.parent_id,
                name = excluded.name,
                type = excluded.type,
                depth = excluded.depth,
                mailbox_id = excluded.mailbox_id,
                status = excluded.status,
                meta_json = excluded.meta_json
            """,
            (
                now,
                now,
                agent_id,
                parent_id,
                name,
                type_,
                depth,
                mailbox_id,
                status,
                json.dumps(meta or {}, separators=(",", ":")),
            ),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


# -------- Mailbox --------

def send_mailbox_message(
    mailbox_id: str,
    sender_agent_id: str,
    message_type: str,
    payload: Dict[str, Any],
    task_id: Optional[int] = None,
    parent_message_id: Optional[int] = None,
    requires_ack: bool = False,
) -> int:
    """
    Enqueue a mailbox message.
    Requires `mailbox_messages` table with columns:
    (created_at, mailbox_id, sender_agent_id, message_type, payload_json, task_id,
     parent_message_id, status, requires_ack, acknowledged_at)
    """
    conn = connect()
    try:
        cur = conn.execute(
            """
            INSERT INTO mailbox_messages(
                created_at, mailbox_id, sender_agent_id, message_type, payload_json,
                task_id, parent_message_id, status, requires_ack, acknowledged_at
            )
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
            """,
            (
                _now(),
                mailbox_id,
                sender_agent_id,
                message_type,
                json.dumps(payload, separators=(",", ":")),
                task_id,
                parent_message_id,
                MAILBOX_PENDING_STATUS,
                1 if requires_ack else 0,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def get_pending_mailbox_messages(mailbox_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    conn = connect()
    try:
        rows = conn.execute(
            """
            SELECT *
            FROM mailbox_messages
            WHERE mailbox_id = ? AND status = ?
            ORDER BY id ASC
            LIMIT ?
            """,
            (mailbox_id, MAILBOX_PENDING_STATUS, limit),
        ).fetchall()

        out: List[Dict[str, Any]] = []
        for r in rows:
            out.append(
                {
                    "id": r["id"],
                    "created_at": r["created_at"],
                    "mailbox_id": r["mailbox_id"],
                    "sender_agent_id": r["sender_agent_id"],
                    "message_type": r["message_type"],
                    "payload": json.loads(r["payload_json"]) if r["payload_json"] else {},
                    "task_id": r["task_id"],
                    "parent_message_id": r["parent_message_id"],
                    "status": r["status"],
                    "requires_ack": bool(r["requires_ack"]),
                    "acknowledged_at": r["acknowledged_at"],
                }
            )
        return out
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