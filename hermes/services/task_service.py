"""
hermes/services/task_service.py
Core logic for managing tasks: queuing, approval, status updates, and retrieval.
"""

from hermes.db import store
from typing import Optional

# Ops-safe policy: these types always require approval
_APPROVAL_REQUIRED_TYPES = {
    "delete_files",
    "reboot_server",
    "restart_service",
    "run_command",
    "modify_config",
}

# Risk score threshold above which approval is required
_APPROVAL_RISK_THRESHOLD = 5

def list_tasks(limit: int = 50, status: str = None) -> list:
    tasks = store.list_tasks(limit=limit, status=status)
    return [_serialize_task(t) for t in tasks]


def get_task(task_id: int) -> dict | None:
    t = store.get_task(task_id)
    if not t:
        return None
    return _serialize_task(t, full=True)


def approve_task(task_id: int) -> dict:
    from hermes.db.store import approve_task as _approve
    try:
        _approve(task_id)
        return {"ok": True, "task_id": task_id}
    except Exception as e:
        return {"ok": False, "task_id": task_id, "error": str(e)}


def deny_task(task_id: int, reason: Optional[str] = None) -> dict:
    from hermes.db.store import deny_task as _deny
    try:
        _deny(task_id, reason=reason)
        return {"ok": True, "task_id": task_id, "reason": reason}
    except Exception as e:
        return {"ok": False, "task_id": task_id, "error": str(e)}

def queue_task(
    type_: str,
    payload: dict = None,
    priority: int = 5,
    risk_score: int = 0,
    requires_approval: bool = False,
) -> dict:
    needs_approval = (
        requires_approval
        or risk_score > _APPROVAL_RISK_THRESHOLD
        or type_ in _APPROVAL_REQUIRED_TYPES
    )

    status = "blocked" if needs_approval else "queued"

    task_id = store.create_task(
        status=status,
        type_=type_,
        title=f"Manual: {type_}",
        payload=payload or {},
        priority=priority,
        requires_approval=needs_approval,
    )

    if needs_approval:
        _notify_approval_required(task_id, type_, payload or {}, risk_score)

    return {"status": status, "task_id": task_id, "requires_approval": needs_approval}


def _notify_approval_required(task_id: int, type_: str, payload: dict, risk_score: int):
    """Fire approval notification via Telegram if configured."""
    import yaml
    try:
        with open("config/plugins.yaml", "r") as f:
            plugins_cfg = yaml.safe_load(f) or {}

        tg_cfg = plugins_cfg.get("plugins", {}).get("telegram", {})
        if not tg_cfg.get("token") or not tg_cfg.get("chat_id"):
            return

        from hermes.plugins.communication.telegram import TelegramCommunicationPlugin
        tg = TelegramCommunicationPlugin(config=tg_cfg)
        tg.send_approval_request(task_id, type_, payload, risk_score)
    except Exception:
        import logging
        logging.getLogger(__name__).exception("Failed to send approval notification")


def list_pending(limit: int = 50) -> list:
    tasks = store.list_tasks(limit=limit, status="blocked")
    return [_serialize_task(t) for t in tasks]


def list_errors(limit: int = 50) -> list:
    tasks = store.list_tasks(limit=limit)
    errors = []
    for t in tasks:
        actions = store.list_actions(task_id=t.id)
        for a in actions:
            if not a.success:
                errors.append({
                    "task_id": t.id,
                    "type": t.type,
                    "tool": a.tool,
                    "error": a.error,
                })
    return errors


def _serialize_task(t, full: bool = False) -> dict:
    row = {
        "id":         t.id,
        "status":     t.status,
        "priority":   t.priority,
        "type":       t.type,
        "title":      t.title,
        "attempts":   t.attempts,
        "created_at": t.created_at,
    }
    if full:
        row.update({
            "updated_at":        t.updated_at,
            "event_id":          t.event_id,
            "requires_approval": t.requires_approval,
            "blocked_reason":    t.blocked_reason,
            "payload":           t.payload,
            "result":            t.result,
        })
    return row