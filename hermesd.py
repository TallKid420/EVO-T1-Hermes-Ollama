import os
import signal
import sys
import yaml
import logging
import threading

from flask import Flask
from werkzeug.serving import make_server

from hermes.db.migrations import migrate
from hermes.daemon.loop import HermesDaemon
from hermes.plugins.loader import PluginManager
from hermes.utils.terminal_handler import configure_terminal_logging
from hermes.watchers.ollama_health import OllamaHealthWatcher
from hermes.watchers.disk_pressure import DiskPressureWatcher
from hermes.watchers.memory_pressure import MemoryPressureWatcher
from hermes.watchers.service_status import ServiceStatusWatcher
from hermes.watchers.chat_watcher import ChatWatcher
from hermes.api.routes import api, init_api

log = logging.getLogger(__name__)

app = Flask(__name__)
app.register_blueprint(api)

_daemon: HermesDaemon = None
_plugin_manager: PluginManager = None
_daemon_lock = threading.Lock()
_stop_event = threading.Event()
_flask_server = None  # werkzeug server reference for clean shutdown


def load_config(path: str) -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f)


def _run_flask(host: str = "0.0.0.0", port: int = 5000):
    global _flask_server
    log.info("REST API starting on %s:%s", host, port)
    _flask_server = make_server(host, port, app)
    _flask_server.serve_forever()  # blocks until shutdown() is called on it
    log.info("REST API stopped")


def _shutdown(reason: str = "unknown"):
    """Single shutdown path — called from signal handler or /shutdown endpoint."""
    log.info("Shutdown triggered: %s", reason)
    with _daemon_lock:
        _daemon._running = False
    if _flask_server:
        _flask_server.shutdown()  # unblocks _run_flask
    _stop_event.set()             # unblocks main thread


def main():
    global _daemon, _plugin_manager

    configure_terminal_logging(log_file="hermes.log")
    migrate()

    config      = load_config("config/services.yaml")
    plugins_cfg = load_config("config/plugins.yaml")
    daemon_cfg  = config.get("daemon", {})
    services    = config["managed_services"]

    watchers = [
        OllamaHealthWatcher(url="http://localhost:11434", timeout=5),
        DiskPressureWatcher(path="/" if sys.platform != "win32" else "C:\\"),
        MemoryPressureWatcher(),
        ServiceStatusWatcher(services=services),
    ]

    _daemon = HermesDaemon(
        watchers=watchers,
        tick_seconds=daemon_cfg.get("tick_seconds", 10),
        dedup_repeat_seconds=daemon_cfg.get("dedup_repeat_seconds", 300),
    )

    _plugin_manager = PluginManager()
    _plugin_manager.load_plugins()

    init_api(_daemon, _daemon_lock, _stop_event, _shutdown)

    # SIGHUP → hot-reload
    def _sighup_handler(signum, frame):
        log.info("SIGHUP received — reloading config")
        with _daemon_lock:
            _daemon.reload_config()

    try:
        signal.signal(signal.SIGHUP, _sighup_handler)
    except AttributeError:
        log.debug("SIGHUP not available on this platform")

    # SIGINT / SIGTERM → clean shutdown
    def _sig_shutdown(signum, frame):
        _shutdown(reason=f"signal {signum}")

    signal.signal(signal.SIGINT, _sig_shutdown)
    signal.signal(signal.SIGTERM, _sig_shutdown)

    # Daemon thread
    daemon_thread = threading.Thread(
        target=_daemon.run_forever,
        name="hermes-daemon",
        daemon=True,
    )
    daemon_thread.start()
    log.info("Daemon thread started")

    # Flask thread
    api_cfg = daemon_cfg.get("api", {})
    flask_thread = threading.Thread(
        target=_run_flask,
        kwargs={
            "host": api_cfg.get("host", "0.0.0.0"),
            "port": api_cfg.get("port", 5000),
        },
        name="hermes-api",
        daemon=True,
    )
    flask_thread.start()
    log.info("REST API thread started")

    terminal_enabled = os.environ.get("HERMES_TERMINAL", "1") != "0"
    if terminal_enabled and sys.stdin.isatty():
        try:
            from main import main as run_rich_terminal
            run_rich_terminal()
        finally:
            _shutdown(reason="terminal exited")
    else:
        _stop_event.wait()

    log.info("Waiting for threads to finish...")
    daemon_thread.join(timeout=15)
    flask_thread.join(timeout=5)

    log.info("Shutting down plugins")
    _plugin_manager.shutdown_all()
    log.info("Hermes stopped.")


if __name__ == "__main__":
    main()