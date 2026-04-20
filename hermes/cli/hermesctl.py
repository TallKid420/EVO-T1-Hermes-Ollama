import argparse
import json

from hermes.db.migrations import migrate
from hermes.db import store
from hermes.db.worker import run_once


def cmd_db_init(_args):
    migrate()
    print("OK: database migrated")


def cmd_events_list(args):
    events = store.list_events(limit=args.limit, unacked_only=args.unacked)
    for e in events:
        print(f"[{e.id}] {e.created_at} {e.severity} {e.type} {e.message} payload={e.payload}")


def cmd_events_add(args):
    payload = json.loads(args.payload) if args.payload else {}
    event_id = store.add_event(
        severity=args.severity,
        source=args.source,
        type_=args.type,
        message=args.message,
        payload=payload,
    )
    print(f"OK: event created id={event_id}")


def cmd_tasks_list(args):
    tasks = store.list_tasks(limit=args.limit, status=args.status)
    for t in tasks:
        print(f"[{t.id}] {t.created_at} {t.status} prio={t.priority} type={t.type} title={t.title} attempts={t.attempts}")


def cmd_tasks_show(args):
    t = store.get_task(args.task_id)
    if not t:
        print("NOT FOUND")
        return
    print(f"id={t.id}")
    print(f"created_at={t.created_at}")
    print(f"updated_at={t.updated_at}")
    print(f"status={t.status}")
    print(f"priority={t.priority}")
    print(f"type={t.type}")
    print(f"title={t.title}")
    print(f"event_id={t.event_id}")
    print(f"attempts={t.attempts}")
    print(f"requires_approval={t.requires_approval}")
    print(f"blocked_reason={t.blocked_reason}")
    print(f"payload={json.dumps(t.payload, indent=2)}")
    print(f"result={json.dumps(t.result, indent=2) if t.result else None}")


def cmd_actions_list(args):
    actions = store.list_actions(task_id=args.task_id, limit=args.limit)
    for a in actions:
        print(
            f"[{a.id}] {a.created_at} task_id={a.task_id} tool={a.tool} action={a.action} "
            f"success={a.success} input={a.input} output={a.output} error={a.error}"
        )

def cmd_tasks_approve(args):
    from hermes.db.store import approve_task
    approve_task(args.task_id)
    print(f"Task {args.task_id} approved — will run on next tick.")


def cmd_tasks_errors(args):
    tasks = store.list_tasks(limit=args.limit)
    found = False
    for t in tasks:
        actions = store.list_actions(task_id=t.id)
        for a in actions:
            if not a.success:
                print(f"Task [{t.id}] {t.type} → error: {a.error}")
                found = True
    if not found:
        print("No errors found.")

def cmd_tasks_queue(args):
    payload = json.loads(args.payload) if args.payload else {}
    task_id = store.create_task(
        type_=args.type,
        title=f"Manual: {args.type}",
        payload=payload,
        priority=args.priority,
        source="manual",
    )
    print(f"OK: task queued id={task_id}")

def cmd_worker_run_once(_args):
    res = run_once()
    print(json.dumps(res, indent=2))

def cmd_db_reset(_args):
    import os
    from hermes.db.conn import get_db_path
    path = get_db_path()
    if os.path.exists(path):
        os.remove(path)
        print(f"OK: deleted {path}")
    migrate()
    print("OK: database re-initialized")

def build_parser():
    p = argparse.ArgumentParser(prog="hermesctl")
    sub = p.add_subparsers(dest="cmd", required=True)

    db = sub.add_parser("db")
    db_sub = db.add_subparsers(dest="sub", required=True)
    db_init = db_sub.add_parser("init")
    db_init.set_defaults(func=cmd_db_init)
    db_reset = db_sub.add_parser("reset")
    db_reset.set_defaults(func=cmd_db_reset)

    ev = sub.add_parser("events")
    ev_sub = ev.add_subparsers(dest="sub", required=True)
    ev_list = ev_sub.add_parser("list")
    ev_list.add_argument("--limit", type=int, default=50)
    ev_list.add_argument("--unacked", action="store_true")
    ev_list.set_defaults(func=cmd_events_list)

    ev_add = ev_sub.add_parser("add")
    ev_add.add_argument("--severity", required=True)
    ev_add.add_argument("--source", default="manual")
    ev_add.add_argument("--type", required=True)
    ev_add.add_argument("--message", required=True)
    ev_add.add_argument("--payload", default="{}")
    ev_add.set_defaults(func=cmd_events_add)

    tk = sub.add_parser("tasks")
    tk_sub = tk.add_subparsers(dest="sub", required=True)
    tk_list = tk_sub.add_parser("list")
    tk_list.add_argument("--limit", type=int, default=50)
    tk_list.add_argument("--status", default=None)
    tk_list.set_defaults(func=cmd_tasks_list)

    tk_show = tk_sub.add_parser("show")
    tk_show.add_argument("task_id", type=int)
    tk_show.set_defaults(func=cmd_tasks_show)

    tk_approve = tk_sub.add_parser("approve", help="Approve a blocked task")
    tk_approve.add_argument("task_id", type=int)
    tk_approve.set_defaults(func=cmd_tasks_approve)

    tk_errors = tk_sub.add_parser("errors", help="Show all failed task errors")
    tk_errors.add_argument("--limit", type=int, default=50)
    tk_errors.set_defaults(func=cmd_tasks_errors)

    ac = sub.add_parser("actions")
    ac_sub = ac.add_subparsers(dest="sub", required=True)
    ac_list = ac_sub.add_parser("list")
    ac_list.add_argument("--task-id", type=int, default=None)
    ac_list.add_argument("--limit", type=int, default=100)
    ac_list.set_defaults(func=cmd_actions_list)

    wk = sub.add_parser("worker")
    wk_sub = wk.add_subparsers(dest="sub", required=True)
    wk_once = wk_sub.add_parser("run-once")
    wk_once.set_defaults(func=cmd_worker_run_once)

    tk_queue = tk_sub.add_parser("queue", help="Manually queue a task")
    tk_queue.add_argument("type", help="Task type e.g. restart_service")
    tk_queue.add_argument("--payload", default="{}")
    tk_queue.add_argument("--priority", type=int, default=5)
    tk_queue.set_defaults(func=cmd_tasks_queue)

    return p


def main():
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()