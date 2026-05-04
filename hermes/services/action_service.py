from hermes.db import store


def list_actions(task_id: int = None, limit: int = 100) -> list:
    actions = store.list_actions(task_id=task_id, limit=limit)
    return [
        {
            "id":         a.id,
            "created_at": a.created_at,
            "task_id":    a.task_id,
            "tool":       a.tool,
            "action":     a.action,
            "success":    a.success,
            "input":      a.input,
            "output":     a.output,
            "error":      a.error,
        }
        for a in actions
    ]