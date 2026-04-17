import json
import time
from typing import Dict, Any, Optional

import yaml

from hermes.db import store
from hermes.db.models import Task
from hermes.executor.autonomous_executor import AutonomousExecutor


def load_services_config(path: str = "config/services.yaml") -> Dict[str, Any]:
    with open(path, "r") as f:
        return yaml.safe_load(f)


def _event_to_task_policy(event_payload: Dict[str, Any], event_type: str, severity: str, event_id: int) -> Optional[int]:
    # Very small v1 policy set (expand later in Planner phase)
    if event_type == "service_unhealthy":
        service = event_payload.get("service")
        if service:
            title = f"Restart service: {service}"
            payload = {"service": service, "reason": "service_unhealthy_event"}
            return store.create_task(
                status="queued",
                priority=100 if severity == "critical" else 50,
                type_="restart_service",
                title=title,
                payload=payload,
                event_id=event_id,
                requires_approval=False,
            )
    return None


def create_tasks_from_recent_events(limit: int = 50) -> int:
    created = 0
    for ev in store.list_events(limit=limit, unacked_only=True):
        task_id = _event_to_task_policy(ev.payload, ev.type, ev.severity, ev.id)
        if task_id:
            created += 1
            # Acknowledge by setting acknowledged_at via a tiny “action” record (simple v1 approach)
            # (Better later: add an explicit store.ack_event(ev.id))
            store.add_action(
                task_id=task_id,
                tool="policy",
                action="event_to_task",
                input_={"event_id": ev.id, "event_type": ev.type},
                output={"task_id": task_id},
                success=True,
            )
            # Mark event acknowledged by writing back directly
            # (keep it here to avoid adding yet another function for v1)
            from hermes.db.conn import connect
            from datetime import datetime
            conn = connect()
            try:
                conn.execute(
                    "UPDATE events SET acknowledged_at = ? WHERE id = ?",
                    (datetime.utcnow().isoformat(), ev.id),
                )
                conn.commit()
            finally:
                conn.close()
    return created


def run_one_task(task: Task, executor: AutonomousExecutor) -> Dict[str, Any]:
    store.update_task_status(task.id, "running")
    store.increment_task_attempts(task.id)

    try:
        if task.type == "restart_service":
            service = task.payload["service"]
            result = executor.restart_service(service)
            success = result.get("status") == "success"
            store.add_action(
                task_id=task.id,
                tool="autonomous_executor",
                action="restart_service",
                input_={"service": service},
                output=result,
                success=success,
                error=None if success else json.dumps(result),
            )
            if success:
                store.set_task_result(task.id, result)
                store.update_task_status(task.id, "done")
            else:
                store.set_task_result(task.id, result)
                store.update_task_status(task.id, "failed")
            return result

        else:
            store.add_action(
                task_id=task.id,
                tool="worker",
                action="unknown_task_type",
                input_={"task_type": task.type},
                output=None,
                success=False,
                error=f"Unknown task type: {task.type}",
            )
            store.update_task_status(task.id, "failed")
            return {"status": "failed", "error": f"Unknown task type: {task.type}"}

    except Exception as e:
        store.add_action(
            task_id=task.id,
            tool="worker",
            action="exception",
            input_={"task_type": task.type},
            output=None,
            success=False,
            error=str(e),
        )
        store.update_task_status(task.id, "failed")
        return {"status": "failed", "error": str(e)}


def run_once():
    created = create_tasks_from_recent_events(limit=50)

    services_cfg = load_services_config()
    executor = AutonomousExecutor(services_cfg)

    queued = store.list_tasks(limit=50, status="queued")
    ran = 0
    for t in queued:
        run_one_task(t, executor)
        ran += 1

    return {"tasks_created": created, "tasks_ran": ran}


def run_forever(interval_seconds: int = 5):
    while True:
        run_once()
        time.sleep(interval_seconds)