from hermes.db import store


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
    _approve(task_id)
    return {"status": "approved", "task_id": task_id}


def queue_task(type_: str, payload: dict = None, priority: int = 5) -> dict:
    task_id = store.create_task(
        status="queued",
        type_=type_,
        title=f"Manual: {type_}",
        payload=payload or {},
        priority=priority,
    )
    return {"status": "queued", "task_id": task_id}


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