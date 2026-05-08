import os
import signal
import sys
import logging
import threading

from hermes.db.migrations import migrate
from hermes.daemon.loop import HermesDaemon
from hermes.plugins.loader import PluginManager
from hermes.utils.terminal_handler import configure_terminal_logging
from hermes.config_loader import load_system_agents
from hermes.agents.factory import AgentFactory
from hermes.agents.system.server_agent import ServerAgent
from hermes.agents.base_agent import BaseAgent
from hermes.watchers.ollama_health import OllamaHealthWatcher
from hermes.watchers.disk_pressure import DiskPressureWatcher
from hermes.watchers.memory_pressure import MemoryPressureWatcher
from hermes.watchers.service_status import ServiceStatusWatcher
from hermes.api.routes import api, init_api
from config.manager import get_daemon_config, load, SERVICES_YAML, PLUGINS_YAML
from hermes.runtime.state import write_pid, clear_pid, is_daemon_running

from flask import Flask
from werkzeug.serving import make_server

log = logging.getLogger(__name__)

server_agents_cfg = load_system_agents("config/agents.yaml")

app = Flask(__name__)
app.register_blueprint(api)

_daemon: HermesDaemon = None
_plugin_manager: PluginManager = None
_daemon_lock = threading.Lock()
_stop_event = threading.Event()
_server_agents = []
_flask_server = None 

for agent in server_agents_cfg:
    _server_agents.append(AgentFactory.spawn(agent))


def _run_flask(host: str = "0.0.0.0", port: int = 5000):
    global _flask_server
    log.info("REST API starting on %s:%s", host, port)
    _flask_server = make_server(host, port, app)
    _flask_server.serve_forever()  # blocks until shutdown() is called on it
    log.info("REST API stopped")


def _shutdown(reason: str = "unknown"):
    log.info("Shutdown triggered: %s", reason)
    with _daemon_lock:
        _daemon._running = False
    if _flask_server:
        _flask_server.shutdown()  # unblocks _run_flask
    _stop_event.set()             # unblocks main thread


def main():
    global _daemon, _plugin_manager

    #Guard: refuse start if already running
    if is_daemon_running():
        log.error("Hermes daemon is already running. Use 'hermes status' to check. \nGoodbye.")
        sys.exit(1)

    configure_terminal_logging(log_file="hermes.log")
    migrate()
    write_pid()

    try: 
        _run_daemon()
    finally:
        clear_pid()
        log.info("Hermes stopped.")

def _run_daemon():
    global _daemon, _plugin_manager

    daemon_cfg = get_daemon_config()
    services_cfg = load(SERVICES_YAML)
    services = services_cfg.get("managed_services", {})
    tick = daemon_cfg.get("tick_seconds", 10)
    dedup = daemon_cfg.get("dedup_repeat_seconds", 300)

    watchers = [
        OllamaHealthWatcher(url="http://localhost:11434", timeout=5),
        DiskPressureWatcher(path="/" if sys.platform != "win32" else "C:\\"),
        MemoryPressureWatcher(),
        ServiceStatusWatcher(services=services),
    ]

    _daemon = HermesDaemon(
        watchers=watchers,
        tick_seconds=tick,
        dedup_repeat_seconds=dedup,
    )

    _plugin_manager = PluginManager()
    _plugin_manager.load_plugins()

    init_api(_daemon, _daemon_lock, _stop_event, _shutdown)

    # SIGHUP → hot-reload
    def _sighup(signum, frame):
        log.info("SIGHUP received — reloading config")
        with _daemon_lock:
            _daemon.reload_config()

    # SIGINT / SIGTERM → clean shutdown
    def _sig_shutdown(signum, frame):
        _shutdown(reason=f"signal {signum}")

    try:
        signal.signal(signal.SIGHUP, _sighup)
    except AttributeError as e:
        log.warning("SIGHUP not supported on this platform, hot-reload disabled")
        log.error(f"Error occurred: \n{e}")
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

    # Flask thread (optional)
    api_cfg = daemon_cfg.get("api", {})
    if api_cfg.get("enabled", True):
        flask_thread = threading.Thread(
            target=_run_flask,
            kwargs={
                #To expose it to the network use 0.0.0.0
                #To set as only local use 127.0.0.1
                "host": api_cfg.get("host", "0.0.0.0"),
                "port": api_cfg.get("port", 5000),
            },
            name="hermes-api",
            daemon=True,
        )
        flask_thread.start()
        log.info("REST API thread started")
    else:
        flask_thread = None
        log.info("REST API disabled by configuration")

    #Block until stop event
    _stop_event.wait()

    log.info("Waiting for threads to finish...")
    daemon_thread.join(timeout=15)
    if flask_thread:
        flask_thread.join(timeout=5)

    log.info("Shutting down plugins")
    _plugin_manager.shutdown_all()


if __name__ == "__main__":
    main()