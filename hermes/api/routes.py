import threading
from flask import Blueprint, jsonify, request

from hermes.services import (
    task_service,
    event_service,
    log_service,
    status_service,
    action_service,
    worker_service,
)

api = Blueprint("api", __name__, url_prefix="/api")

_daemon = None
_daemon_lock = None
_stop_event = None
_shutdown_fn = None

def init_api(daemon, lock, stop_event, shutdown_fn):
    global _daemon, _daemon_lock, _stop_event, _shutdown_fn
    _daemon = daemon
    _daemon_lock = lock
    _stop_event = stop_event
    _shutdown_fn = shutdown_fn


# ── Status ─────────────────────────────────────────────────────────────────────

@api.route("/status", methods=["GET"])
def status():
    return jsonify(status_service.get_status())


# ── Logs ───────────────────────────────────────────────────────────────────────

@api.route("/logs", methods=["GET"])
def logs():
    result = log_service.read_logs(
        log_path=request.args.get("file", "hermes.log"),
        lines_n=int(request.args.get("lines", 100)),
        filter_=request.args.get("filter", None),
        level=request.args.get("level", None),
    )
    if "error" in result:
        return jsonify(result), 404
    return jsonify(result)


# ── Tasks ──────────────────────────────────────────────────────────────────────

@api.route("/tasks", methods=["GET"])
def tasks_list():
    return jsonify(task_service.list_tasks(
        limit=int(request.args.get("limit", 50)),
        status=request.args.get("status", None),
    ))


@api.route("/tasks/pending", methods=["GET"])
def tasks_pending():
    return jsonify(task_service.list_pending(
        limit=int(request.args.get("limit", 50))
    ))


@api.route("/tasks/errors", methods=["GET"])
def tasks_errors():
    return jsonify(task_service.list_errors(
        limit=int(request.args.get("limit", 50))
    ))


@api.route("/tasks/<int:task_id>", methods=["GET"])
def tasks_show(task_id):
    t = task_service.get_task(task_id)
    if not t:
        return jsonify({"error": "not found"}), 404
    return jsonify(t)


@api.route("/tasks/<int:task_id>/approve", methods=["POST"])
def tasks_approve(task_id):
    return jsonify(task_service.approve_task(task_id))


@api.route("/tasks/queue", methods=["POST"])
def tasks_queue():
    body = request.get_json(force=True)
    if not body.get("type"):
        return jsonify({"error": "type is required"}), 400
    return jsonify(task_service.queue_task(
        type_=body["type"],
        payload=body.get("payload", {}),
        priority=body.get("priority", 5),
    )), 201


# ── Events ─────────────────────────────────────────────────────────────────────

@api.route("/events", methods=["GET"])
def events_list():
    return jsonify(event_service.list_events(
        limit=int(request.args.get("limit", 50)),
        unacked_only=request.args.get("unacked", "false").lower() == "true",
    ))


@api.route("/events", methods=["POST"])
def events_add():
    body = request.get_json(force=True)
    return jsonify(event_service.add_event(
        severity=body.get("severity"),
        source=body.get("source", "api"),
        type_=body.get("type"),
        message=body.get("message"),
        payload=body.get("payload", {}),
    )), 201


# ── Actions ────────────────────────────────────────────────────────────────────

@api.route("/actions", methods=["GET"])
def actions_list():
    return jsonify(action_service.list_actions(
        task_id=int(request.args.get("task_id")) if request.args.get("task_id") else None,
        limit=int(request.args.get("limit", 100)),
    ))


# ── Worker ─────────────────────────────────────────────────────────────────────

@api.route("/worker/run", methods=["POST"])
def worker_run():
    return jsonify(worker_service.run_worker_once())


# ── Daemon control ─────────────────────────────────────────────────────────────

@api.route("/reload", methods=["POST"])
def reload():
    with _daemon_lock:
        _daemon.reload_config()
    return jsonify({"status": "reloaded"})


@api.route("/shutdown", methods=["POST"])
def shutdown():
    threading.Thread(target=_shutdown_fn, kwargs={"reason": "REST /shutdown"}, daemon=True).start()
    return jsonify({"status": "shutting down"})