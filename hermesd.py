import signal
import yaml
import logging
import time
import threading

from hermes.chat.message_handler import handle_user_message
from hermes.db.migrations import migrate
from hermes.daemon.loop import HermesDaemon
from hermes.plugins.loader import PluginManager
from hermes.utils.terminal_handler import configure_terminal_logging
from hermes.watchers.ollama_health import OllamaHealthWatcher
from hermes.watchers.disk_pressure import DiskPressureWatcher
from hermes.watchers.memory_pressure import MemoryPressureWatcher
from hermes.watchers.service_status import ServiceStatusWatcher
from hermes.watchers.chat_watcher import ChatWatcher



log = logging.getLogger(__name__)


def load_config(path: str) -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f)


def main():
    configure_terminal_logging(log_file="hermes.log")

    # Ensure DB is ready
    migrate()

    config = load_config("config/services.yaml")
    plugins_cfg = load_config("config/plugins.yaml")
    chat_watcher_cfg = {
        "telegram": {
            **plugins_cfg.get("plugins", {}).get("telegram", {}),
            "input": plugins_cfg.get("active", {}).get("communication", {}).get("telegram", {}).get("input", False),
        }
    }
    daemon_cfg = config.get("daemon", {})
    services = config["managed_services"]

    watchers = [
        OllamaHealthWatcher(url="http://localhost:11434", timeout=5),
        DiskPressureWatcher(path="/" if __import__("sys").platform != "win32" else "C:\\"),
        MemoryPressureWatcher(),
        ServiceStatusWatcher(services=services),

    ]

    daemon = HermesDaemon(
        watchers=watchers,
        tick_seconds=daemon_cfg.get("tick_seconds", 10),
        dedup_repeat_seconds=daemon_cfg.get("dedup_repeat_seconds", 300),
    )

    chat_watcher = ChatWatcher(cfg=chat_watcher_cfg)

    def _chat_loop():
        while True:
            try:
                result = chat_watcher.check()
                if result.triggered:
                    handle_user_message(result, daemon.plugins_cfg, daemon.agents_cfg)
            except Exception:
                log.exception("Unhandled exception in chat loop")
            time.sleep(0.1)

    chat_thread = threading.Thread(target=_chat_loop, daemon=True)
    chat_thread.start()
    log.info("Chat watcher thread started")

    plugin_manager = PluginManager()
    plugin_manager.load_plugins()

    # SIGHUP → hot-reload config (Linux/macOS). No-op on Windows.
    def _sighup_handler(signum, frame):
        log.info("SIGHUP received — reloading config")
        daemon.reload_config()

    try:
        signal.signal(signal.SIGHUP, _sighup_handler)
    except AttributeError:
        # Windows does not have SIGHUP
        log.debug("SIGHUP not available on this platform; hot-reload via signal disabled")

    try:
        daemon.run_forever()
    except KeyboardInterrupt:
        log.info("Received shutdown signal, exiting...")
    finally:
        log.info("Shutting down plugins")
        plugin_manager.shutdown_all()

if __name__ == "__main__":
    main()