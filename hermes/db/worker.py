from hermes.executor.autonomous_executor import AutonomousExecutor
from hermes.notifications.handler import NotificationHandler
from hermes.core.permissions import ApprovalRequired
from hermes.db.verifier import VerifierAgent
from hermes.agents.planner import Planner
from hermes.db.conn import connect
from hermes.db.models import Task
from datetime import datetime
from hermes.db import store

import logging
log = logging.getLogger(__name__)
from typing import Dict, Any, Optional, List

import json
import time
import yaml


def load_services_config(path: str = "config/services.yaml") -> Dict[str, Any]:
    with open(path, "r") as f:
        return yaml.safe_load(f)


def _recent_action_history(limit: int = 20) -> List[Dict[str, Any]]:
    history: List[Dict[str, Any]] = []
    for action in reversed(store.list_actions(limit=limit)):
        history.append(
            {
                "timestamp": action.created_at,
                "action": action.action,
                "result": action.output if action.output is not None else {"success": action.success},
            }
        )
    return history


def _event_to_task_policy(
    planner: Planner,
    event_payload: Dict[str, Any],
    event_type: str,
    severity: str,
    event_id: int,
) -> Optional[int]:

    plan = planner.plan(
        event={
            "type": event_type,
            "severity": severity,
            "message": f"{event_type}: {event_payload}",
            "payload": event_payload,
        },
        system_status={},
        action_history=_recent_action_history(limit=planner.max_history),
    )

    action = plan["action"]
    action_args = plan.get("action_args", {})
    needs_approval = plan.get("requires_approval", False)
    risk_score = plan.get("risk_score", 5)

    # Map plan → task
    if action == "restart_service":
        service = action_args.get("service") or event_payload.get("service")
        if not service:
            return None
        return store.create_task(
            status="blocked" if needs_approval else "queued",
            priority=100 if risk_score <= 3 else 50,
            type_="restart_service",
            title=f"Restart service: {service}",
            payload={"service": service, "reason": event_type},
            event_id=event_id,
            requires_approval=needs_approval,
        )

    elif action == "cleanup_cache":
        path = action_args.get("path", "/var/lib/hermes/cache")
        return store.create_task(
            status="blocked" if needs_approval else "queued",
            priority=50,
            type_="cleanup_cache",
            title=f"Cleanup cache: {path}",
            payload={"path": path, "reason": event_type},
            event_id=event_id,
            requires_approval=needs_approval,
        )

    elif action in ("send_notification", "notify_user"):
        message = action_args.get("message", plan.get("reasoning", event_type))
        return store.create_task(
            status="queued",
            priority=10,
            type_="send_notification",
            title=f"Notify: {message[:60]}",
            payload={"message": message, "reason": event_type},
            event_id=event_id,
            requires_approval=False,
        )

    return None


def create_tasks_from_recent_events(limit: int = 50) -> int:
    created = 0
    planner = Planner()
    for ev in store.list_events(limit=limit, unacked_only=True):
        task_id = _event_to_task_policy(planner, ev.payload, ev.type, ev.severity, ev.id)
        if task_id:
            created += 1
            store.add_action(
                task_id=task_id,
                tool="policy",
                action="event_to_task",
                input_={"event_id": ev.id, "event_type": ev.type},
                output={"task_id": task_id},
                success=True,
            )
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


def _to_verifier_task(task: Task) -> Dict[str, Any]:
    if task.type == "restart_service":
        return {"action": "restart_service", "action_args": {"service": task.payload.get("service")}}
    if task.type == "cleanup_cache":
        return {"action": "cleanup_cache", "action_args": {"path": task.payload.get("path")}}
    if task.type == "send_notification":
        return {"action": "send_notification", "action_args": {"message": task.payload.get("message")}}
    return {"action": task.type, "action_args": {}}


def _apply_verification(task: Task, result: Dict[str, Any], verifier: Optional[VerifierAgent]) -> bool:
    if verifier is None:
        return True
    if task.type not in {"restart_service", "cleanup_cache"}:
        return True

    verification = verifier.verify(task=_to_verifier_task(task), result=result)
    store.add_action(
        task_id=task.id,
        tool="verifier",
        action="verify_result",
        input_={"task_type": task.type},
        output={
            "success": verification.success,
            "method": verification.method,
            "message": verification.message,
            "next_action": verification.next_action,
            "requires_approval": verification.requires_approval,
        },
        success=verification.success,
        error=None if verification.success else verification.message,
    )

    if verification.success:
        return True

    if verification.next_action == "send_notification":
        store.create_task(
            status="queued",
            priority=20,
            type_="send_notification",
            title=f"Verification alert for task {task.id}",
            payload={"message": f"Verification failed for task {task.id}: {verification.message}"},
            event_id=task.event_id,
            requires_approval=False,
        )

    if verification.requires_approval:
        store.update_task_status(task.id, "blocked", blocked_reason=verification.message)
    else:
        store.update_task_status(task.id, "failed", blocked_reason=verification.message)
    return False

def run_one_task(
    task: Task,
    executor: AutonomousExecutor,
    verifier: Optional[VerifierAgent] = None,
    notification_handler: Optional[NotificationHandler] = None,
) -> Dict[str, Any]:

    try:
        if task.type == "restart_service":
            service = task.payload["service"]

            # DUPLICATE CHECK — before executing, not after
            existing = [
                t for t in store.list_tasks(limit=100)
                if t.type == "restart_service"
                and t.status in ("queued", "blocked", "running")
                and t.id != task.id
            ]
            if any(t.id != task.id and t.payload.get("service") == service for t in existing):
                log.info(f"Skipping duplicate restart_service task for {service}")
                store.update_task_status(task.id, "done")
                return {"status": "skipped_duplicate"}

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
            store.set_task_result(task.id, result)
            if success and _apply_verification(task, result, verifier):
                store.update_task_status(task.id, "done")
            elif not success:
                store.update_task_status(task.id, "failed")
            return result

        elif task.type == "cleanup_cache":
            path = task.payload.get("path", "/var/lib/hermes/cache")
            result = executor.cleanup_path(path)
            success = result.get("status") == "success"
            store.add_action(
                task_id=task.id,
                tool="autonomous_executor",
                action="cleanup_path",
                input_={"path": path},
                output=result,
                success=success,
                error=None if success else json.dumps(result),
            )
            store.set_task_result(task.id, result)
            if success and _apply_verification(task, result, verifier):
                store.update_task_status(task.id, "done")
            elif not success:
                store.update_task_status(task.id, "failed")
            return result

        elif task.type == "send_notification":
            msg = task.payload.get("message", task.title)
            notifier = notification_handler or NotificationHandler()
            notifier.send_notification(msg, severity="Severity.INFO")
            store.add_action(
                task_id=task.id,
                tool="notification_handler",
                action="send_notification",
                input_={"message": msg},
                output={"status": "sent"},
                success=True,
                error=None,
            )
            store.set_task_result(task.id, {"status": "sent"})
            store.update_task_status(task.id, "done")
            return {"status": "sent"}

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

    except ApprovalRequired as e:
        store.update_task_status(task.id, "blocked", blocked_reason=str(e))
        log.warning(f"Task {task.id} blocked: {e}")
        return {"status": "blocked", "error": str(e)}

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
    planner = Planner()
    notifier = NotificationHandler()
    verifier = VerifierAgent(
        planner=planner,
        notifier=notifier,
        allowlist=planner.allowed_actions,
    )

    ran = 0
    for _ in range(50):
        t = store.claim_next_queued_task()
        if t is None:
            break
        run_one_task(t, executor, verifier=verifier, notification_handler=notifier)
        ran += 1

    return {"tasks_created": created, "tasks_ran": ran}


def run_forever(interval_seconds: int = 5):
    while True:
        run_once()
        time.sleep(interval_seconds)