import yaml
import logging

from hermes.db.migrations import migrate
from hermes.daemon.loop import HermesDaemon
from hermes.plugins.loader import PluginManager
from hermes.utils.terminal_handler import configure_terminal_logging
from hermes.watchers.ollama_health import OllamaHealthWatcher
from hermes.watchers.disk_pressure import DiskPressureWatcher
from hermes.watchers.memory_pressure import MemoryPressureWatcher
from hermes.watchers.service_status import ServiceStatusWatcher
from hermes.chat.chat_listener import ChatListener


log = logging.getLogger(__name__)


def load_config(path="config/services.yaml"):
    with open(path, "r") as f:
        return yaml.safe_load(f)


def main():
    configure_terminal_logging(log_file="hermes.log")

    # Ensure DB is ready
    migrate()

    config = load_config()
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
    plugin_manager = PluginManager()
    plugin_manager.load_plugins()

    try:
        daemon.run_forever()
    except KeyboardInterrupt:
        log.info("Received shutdown signal, exiting...")
    finally:
        log.info("Shutting down plugins")
        plugin_manager.shutdown_all()


if __name__ == "__main__":
    main()