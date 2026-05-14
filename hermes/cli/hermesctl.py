import argparse
import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
import yaml

from config.manager import load, save, SERVICES_YAML, AGENTS_YAML
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm

from hermes.db.migrations import migrate
from hermes.db import store
from hermes.db.worker import run_once
from hermes.runtime.state import PID_FILE, get_daemon_pid, is_daemon_running


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

_SEV_COLOR = {
    "critical": "\033[31m",   # red
    "warning":  "\033[33m",   # yellow
    "info":     "\033[32m",   # green
}
_RESET = "\033[0m"
_BOLD = "\033[1m"
console = Console()

def _c(text: str, color_code: str) -> str:
    """Wrap text in ANSI color if stdout is a TTY."""
    if sys.stdout.isatty():
        return f"{color_code}{text}{_RESET}"
    return text


def _sev(severity: str) -> str:
    code = _SEV_COLOR.get(str(severity).lower(), "")
    return _c(str(severity).upper(), code) if code else str(severity).upper()


def _table(rows: list[dict], cols: list[str]) -> None:
    """Print a simple fixed-width table."""
    if not rows:
        print("  (none)")
        return
    widths = {c: len(c) for c in cols}
    for row in rows:
        for c in cols:
            widths[c] = max(widths[c], len(str(row.get(c, ""))))
    header = "  ".join(c.ljust(widths[c]) for c in cols)
    sep    = "  ".join("-" * widths[c]  for c in cols)
    print(_c(header, _BOLD))
    print(sep)
    for row in rows:
        print("  ".join(str(row.get(c, "")).ljust(widths[c]) for c in cols))


def _daemon_base_url() -> str:
    host = "127.0.0.1"
    port = 5000
    try:
        cfg = load(SERVICES_YAML)
        daemon = cfg.get("daemon", {}) if isinstance(cfg, dict) else {}
        api = cfg.get("api", {}) if isinstance(cfg, dict) else {}
        flask = cfg.get("flask", {}) if isinstance(cfg, dict) else {}
        merged = dict(api)
        merged.update(flask)
        merged.update(daemon.get("api", {}))
        host = str(merged.get("host", host))
        port = int(merged.get("port", port))
    except Exception:
        pass
    if host in ("0.0.0.0", "::"):
        host = "127.0.0.1"
    return f"http://{host}:{port}"


def _daemon_ping(timeout: float = 1.5) -> tuple[bool, str]:
    base = _daemon_base_url()
    try:
        with urllib.request.urlopen(f"{base}/api/status", timeout=timeout) as resp:
            ok = 200 <= getattr(resp, "status", 0) < 300
            return ok, base
    except urllib.error.HTTPError:
        return True, base
    except urllib.error.URLError:
        return False, base
    except Exception:
        return False, base


def _port_in_use(host: str, port: int) -> bool:
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            return s.connect_ex((host, port)) == 0
    except OSError:
        return False


def _ensure_valid_config() -> None:
    services = load(SERVICES_YAML) if os.path.exists(SERVICES_YAML) else {}
    agents = load(AGENTS_YAML) if os.path.exists(AGENTS_YAML) else {}

    daemon = services.setdefault("daemon", {})
    flask = services.setdefault("flask", {})

    needs_wizard = False
    if not os.path.exists(SERVICES_YAML) or not os.path.exists(AGENTS_YAML):
        needs_wizard = True

    planner_cfg = (agents.get("system_agents") or {}).get("planner") or {}
    required_planner = ["provider", "endpoint", "model", "timeout_seconds", "max_history", "allowed_actions", "rules"]
    if any(planner_cfg.get(k) in (None, "", "not-set") for k in required_planner):
        needs_wizard = True

    if flask.get("enabled") not in (True, False):
        needs_wizard = True

    if daemon.get("tick_seconds") is None or daemon.get("dedup_repeat_seconds") is None:
        needs_wizard = True

    if not needs_wizard:
        return

    console.print(Panel("[bold cyan]Hermes First-Run Wizard[/bold cyan]"))

    endpoint = Prompt.ask("Ollama endpoint", default=planner_cfg.get("endpoint") or "http://127.0.0.1:11434").strip()
    model = Prompt.ask("Default model", default=planner_cfg.get("model") or "llama3.1").strip()

    flask_enabled = Confirm.ask("Enable Flask API?", default=bool(flask.get("enabled", True)))
    flask_host = "127.0.0.1"
    flask_port = int(flask.get("port", 5000) or 5000)
    if flask_enabled:
        flask_host = Prompt.ask("Flask host", default=str(flask.get("host") or "127.0.0.1")).strip() or "127.0.0.1"
        while True:
            raw_port = Prompt.ask("Flask port", default=str(flask_port)).strip()
            try:
                flask_port = int(raw_port)
            except ValueError:
                console.print("[yellow]Please enter a valid port.[/yellow]")
                continue
            if _port_in_use(flask_host, flask_port):
                console.print(f"[yellow]Port {flask_port} is in use on {flask_host}. Choose another.[/yellow]")
                continue
            break

    telegram_token = Prompt.ask("Telegram token (optional)", default="").strip()

    daemon.setdefault("tick_seconds", 10)
    daemon.setdefault("dedup_repeat_seconds", 300)
    daemon["pid_file"] = "/tmp/hermes.pid"

    services["flask"] = {
        "enabled": flask_enabled,
        "host": flask_host,
        "port": flask_port,
    }

    system_agents = agents.setdefault("system_agents", {})
    planner = system_agents.setdefault("planner", {})
    planner["provider"] = "ollama"
    planner["endpoint"] = endpoint
    planner["model"] = model
    planner["timeout_seconds"] = int(planner.get("timeout_seconds") or 20)
    planner["max_history"] = int(planner.get("max_history") or 5)
    planner.setdefault("allowed_actions", ["restart_service", "cleanup_cache", "send_notification", "verify_service"])
    planner.setdefault("rules", [
        "If risk_score >= 7, set requires_approval to true",
        "If the same action has failed more than 2 times in history, escalate instead of retrying",
        "Always respond in valid JSON only",
        "Never suggest actions outside the allowed_actions list",
    ])

    if telegram_token:
        plugins_path = os.path.join("config", "plugins.yaml")
        plugins = load(plugins_path) if os.path.exists(plugins_path) else {}
        plugins.setdefault("plugins", {})
        plugins.setdefault("active", {}).setdefault("communication", {})
        plugins["active"]["communication"].setdefault("telegram", {})
        plugins["plugins"].setdefault("telegram", {})
        plugins["plugins"]["telegram"]["token"] = telegram_token
        save(plugins_path, plugins)

    save(SERVICES_YAML, services)
    save(AGENTS_YAML, agents)
    console.print("[green]Configuration validated and saved.[/green]")


def _ensure_flask_port_available() -> None:
    cfg = load(SERVICES_YAML) if os.path.exists(SERVICES_YAML) else {}
    if not isinstance(cfg, dict):
        return

    daemon = cfg.get("daemon", {}) or {}
    flask = cfg.get("flask", {}) or {}
    merged = dict(flask)
    merged.update(daemon.get("api", {}))

    if not bool(merged.get("enabled", True)):
        return

    host = str(merged.get("host", "127.0.0.1"))
    if host in ("", "::"):
        host = "127.0.0.1"
    port = int(merged.get("port", 5000))

    if not _port_in_use(host, port):
        return

    console.print(f"[yellow]Configured Flask port {port} on {host} is already in use.[/yellow]")
    while True:
        raw_port = Prompt.ask("Choose an alternative Flask port", default=str(port + 1)).strip()
        try:
            new_port = int(raw_port)
        except ValueError:
            console.print("[yellow]Please enter a valid port.[/yellow]")
            continue
        if _port_in_use(host, new_port):
            console.print(f"[yellow]Port {new_port} is also in use on {host}.[/yellow]")
            continue
        cfg.setdefault("flask", {})
        cfg["flask"]["enabled"] = True
        cfg["flask"]["host"] = host
        cfg["flask"]["port"] = new_port
        save(SERVICES_YAML, cfg)
        console.print(f"[green]Updated Flask port to {new_port} in {SERVICES_YAML}.[/green]")
        return


def _show_operator_console() -> None:
    from main import main as tui_main
    tui_main()


# ---------------------------------------------------------------------------
# hermesctl status
# ---------------------------------------------------------------------------

def cmd_status(args):
    pid = get_daemon_pid()
    running, base_url = _daemon_ping(timeout=1.2)
    if pid:
        state = _c("RUNNING", "\033[32m")
        print(f"\n{_c('Hermesd', _BOLD)}  {state}  pid={pid}  ({base_url})")
    else:
        state = _c("STOPPED", "\033[31m")
        print(f"\n{_c('Hermesd', _BOLD)}  {state}  ({PID_FILE})")

    from hermes.agents.types.monitor_agent import MonitorAgent
    agent = MonitorAgent.from_config()
    status = agent.get_status()

    overall = _c("HEALTHY", "\033[32m") if status.overall_healthy else _c(
        f"DEGRADED ({status.overall_severity.upper()})", "\033[31m"
    )
    print(f"\n{_c('System Status', _BOLD)}  {overall}\n")

    rows = [
        {
            "watcher": w.name,
            "status": "OK" if w.healthy else "ALERT",
            "severity": w.severity.upper(),
            "message": w.message,
        }
        for w in status.watchers
    ]
    _table(rows, ["watcher", "status", "severity", "message"])
    print()

    if status.alerts:
        print(_c("Alerts:", _BOLD))
        for a in status.alerts:
            print(f"  {_sev(a.severity)}  {a.name}: {a.message}")
        print()


# ---------------------------------------------------------------------------
# hermesctl tasks  (extended)
# ---------------------------------------------------------------------------

def cmd_tasks_list(args):
    tasks = store.list_tasks(limit=args.limit, status=args.status)
    rows = [
        {
            "id":       t.id,
            "status":   t.status,
            "priority": t.priority,
            "type":     t.type,
            "title":    t.title[:48],
            "attempts": t.attempts,
            "created":  t.created_at[:19],
        }
        for t in tasks
    ]
    _table(rows, ["id", "status", "priority", "type", "title", "attempts", "created"])


def cmd_tasks_pending(args):
    """Show tasks waiting for approval."""
    tasks = store.list_tasks(limit=args.limit, status="blocked")
    if not tasks:
        print("No tasks pending approval.")
        return
    rows = [
        {
            "id":     t.id,
            "type":   t.type,
            "title":  t.title[:56],
            "reason": t.blocked_reason or "",
            "created": t.created_at[:19],
        }
        for t in tasks
    ]
    _table(rows, ["id", "type", "title", "reason", "created"])


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
        status="queued",
        type_=args.type,
        title=f"Manual: {args.type}",
        payload=payload,
        priority=args.priority,
    )
    print(f"OK: task queued id={task_id}")


def cmd_start(args):
    _ensure_valid_config()
    _ensure_flask_port_available()
    if is_daemon_running():
        pid = get_daemon_pid()
        print(f"Hermesd already running (pid={pid}). Attaching console.")
        _show_operator_console()
        return

    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    kwargs = {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "stdin": subprocess.DEVNULL,
    }
    if creationflags:
        kwargs["creationflags"] = creationflags
    else:
        kwargs["start_new_session"] = True
    env = os.environ.copy()
    env["HERMES_TERMINAL"] = "0"
    subprocess.Popen([sys.executable, "hermesd.py"], env=env, **kwargs)

    for _ in range(30):
        time.sleep(0.2)
        if is_daemon_running():
            print(f"Hermesd started (pid={get_daemon_pid()}).")
            _show_operator_console()
            return

    print("Hermesd start requested, but PID file was not observed yet.")


def cmd_stop(_args):
    pid = get_daemon_pid()
    if not pid:
        print("Hermesd is not running.")
        return
    try:
        os.kill(pid, signal.SIGTERM)
        print(f"Sent SIGTERM to Hermesd pid={pid}.")
    except ProcessLookupError:
        print("Process no longer exists.")
        return
    except Exception as exc:
        print(f"Failed to stop daemon: {exc}")
        return

    for _ in range(30):
        time.sleep(0.2)
        if not is_daemon_running():
            print("Hermesd stopped.")
            return

    print("Stop signal sent, but daemon still appears to be running.")


def cmd_attach(_args):
    if not is_daemon_running():
        print("Hermesd is not running. Start it first.")
        return
    _show_operator_console()



def cmd_logs(args):
    """Read hermes.log — tail the last N lines, with optional keyword filter."""
    log_path = args.file
    if not os.path.exists(log_path):
        print(f"Log file not found: {log_path}")
        sys.exit(1)

    if args.follow:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            f.seek(0, os.SEEK_END)
            try:
                while True:
                    line = f.readline()
                    if not line:
                        time.sleep(0.2)
                        continue
                    line = line.rstrip()
                    if args.filter and args.filter.lower() not in line.lower():
                        continue
                    if args.level and args.level.upper() not in line:
                        continue
                    if sys.stdout.isatty():
                        if "CRITICAL" in line or "ERROR" in line:
                            print(_c(line, "\033[31m"))
                        elif "WARNING" in line:
                            print(_c(line, "\033[33m"))
                        else:
                            print(line)
                    else:
                        print(line)
            except KeyboardInterrupt:
                return

    with open(log_path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    if args.filter:
        needle = args.filter.lower()
        lines = [l for l in lines if needle in l.lower()]

    if args.level:
        lvl = args.level.upper()
        lines = [l for l in lines if lvl in l]

    tail = lines[-args.lines:]

    for line in tail:
        line = line.rstrip()
        if sys.stdout.isatty():
            if "CRITICAL" in line or "ERROR" in line:
                print(_c(line, "\033[31m"))
            elif "WARNING" in line:
                print(_c(line, "\033[33m"))
            else:
                print(line)
        else:
            print(line)


# ---------------------------------------------------------------------------
# Existing helpers kept intact
# ---------------------------------------------------------------------------

def cmd_db_init(_args):
    migrate()
    print("OK: database migrated")


def cmd_events_list(args):
    events = store.list_events(limit=args.limit, unacked_only=args.unacked)
    rows = [
        {
            "id":       e.id,
            "at":       e.created_at[:19],
            "severity": e.severity,
            "type":     e.type,
            "source":   e.source,
            "message":  e.message[:60],
        }
        for e in events
    ]
    _table(rows, ["id", "at", "severity", "type", "source", "message"])


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


def cmd_actions_list(args):
    actions = store.list_actions(task_id=args.task_id, limit=args.limit)
    for a in actions:
        print(
            f"[{a.id}] {a.created_at} task_id={a.task_id} tool={a.tool} action={a.action} "
            f"success={a.success} input={a.input} output={a.output} error={a.error}"
        )


def cmd_worker_run_once(_args):
    res = run_once()
    print(json.dumps(res, indent=2))


def cmd_db_reset(_args):
    from hermes.db.conn import get_db_path
    path = get_db_path()
    if os.path.exists(path):
        os.remove(path)
        print(f"OK: deleted {path}")
    migrate()
    print("OK: database re-initialized")

def cmd_chat(args):
    _show_operator_console()


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def build_parser():
    p = argparse.ArgumentParser(prog="hermesctl")
    sub = p.add_subparsers(dest="cmd", required=True)

    st = sub.add_parser("status", help="Live system health snapshot")
    st.set_defaults(func=cmd_status)

    dm = sub.add_parser("start", help="Start hermesd then attach console")
    dm.set_defaults(func=cmd_start)

    sp = sub.add_parser("stop", help="Stop hermesd")
    sp.set_defaults(func=cmd_stop)

    at = sub.add_parser("attach", help="Attach operator console to running daemon")
    at.set_defaults(func=cmd_attach)

    lg = sub.add_parser("logs", help="Read the Hermes log file")
    lg.add_argument("-n", "--lines", type=int, default=50, help="Number of lines to show (default 50)")
    lg.add_argument("-f", "--filter", default=None, help="Only show lines containing this string")
    lg.add_argument("--level", default=None, choices=["DEBUG","INFO","WARNING","ERROR","CRITICAL"],
                    help="Filter by log level")
    lg.add_argument("--file", default="hermes.log", help="Path to log file (default hermes.log)")
    lg.add_argument("--follow", action="store_true", help="Stream new lines as they are written")
    lg.set_defaults(func=cmd_logs)

    # --- tasks ---
    tk = sub.add_parser("tasks", help="Manage tasks")
    tk_sub = tk.add_subparsers(dest="sub", required=True)

    tk_list = tk_sub.add_parser("list", help="List recent tasks")
    tk_list.add_argument("--limit", type=int, default=50)
    tk_list.add_argument("--status", default=None)
    tk_list.set_defaults(func=cmd_tasks_list)

    tk_pending = tk_sub.add_parser("pending", help="Tasks awaiting approval")
    tk_pending.add_argument("--limit", type=int, default=50)
    tk_pending.set_defaults(func=cmd_tasks_pending)

    tk_show = tk_sub.add_parser("show", help="Show full task detail")
    tk_show.add_argument("task_id", type=int)
    tk_show.set_defaults(func=cmd_tasks_show)

    tk_approve = tk_sub.add_parser("approve", help="Approve a blocked task")
    tk_approve.add_argument("task_id", type=int)
    tk_approve.set_defaults(func=cmd_tasks_approve)

    tk_errors = tk_sub.add_parser("errors", help="Show all failed task errors")
    tk_errors.add_argument("--limit", type=int, default=50)
    tk_errors.set_defaults(func=cmd_tasks_errors)

    tk_queue = tk_sub.add_parser("queue", help="Manually queue a task")
    tk_queue.add_argument("type", help="Task type e.g. restart_service")
    tk_queue.add_argument("--payload", default="{}")
    tk_queue.add_argument("--priority", type=int, default=5)
    tk_queue.set_defaults(func=cmd_tasks_queue)

    # --- events ---
    ev = sub.add_parser("events", help="Manage events")
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

    # # --- configure ---
    # cfg = sub.add_parser("config", help="Configure Hermes Settings")
    # cfg_sub = cfg.add_subparsers(dest="sub", required=True)

    # cfg_onboard = cfg_sub.add_parser("onboard", help="Onboard a new provider or model")
    # cfg_onboard.set_defaults(func=cmd_config_onboard)

    # cfg_model = cfg_sub.add_parser("model", help="Manage model configurations")
    # cfg_model.add_argument("--list", action="")
    # cfg_model.set_defaults(func=cmd_config_model)
    
    # --- run ---
    chat = sub.add_parser("run", help="Chat with an agent")
    chat_sub = chat.add_subparsers(dest="sub", required=False)
    chat.set_defaults(func=cmd_chat)


    # --- actions ---
    ac = sub.add_parser("actions", help="View executor action history")
    ac_sub = ac.add_subparsers(dest="sub", required=True)
    ac_list = ac_sub.add_parser("list")
    ac_list.add_argument("--task-id", type=int, default=None)
    ac_list.add_argument("--limit", type=int, default=100)
    ac_list.set_defaults(func=cmd_actions_list)

    # --- worker ---
    wk = sub.add_parser("worker", help="Low-level worker control")
    wk_sub = wk.add_subparsers(dest="sub", required=True)
    wk_once = wk_sub.add_parser("run-once")
    wk_once.set_defaults(func=cmd_worker_run_once)

    # --- db ---
    db = sub.add_parser("db", help="Database maintenance")
    db_sub = db.add_subparsers(dest="sub", required=True)
    db_init = db_sub.add_parser("init")
    db_init.set_defaults(func=cmd_db_init)
    db_reset = db_sub.add_parser("reset")
    db_reset.set_defaults(func=cmd_db_reset)

    return p

def main(*argv):
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main(*sys.argv[1:])