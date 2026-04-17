import yaml

from hermes.db.migrations import migrate
from hermes.daemon.loop import HermesDaemon
from hermes.watchers.ollama_health import OllamaHealthWatcher
from hermes.watchers.disk_pressure import DiskPressureWatcher
from hermes.watchers.memory_pressure import MemoryPressureWatcher
from hermes.watchers.service_status import ServiceStatusWatcher


def load_config(path="config/services.yaml"):
    with open(path, "r") as f:
        return yaml.safe_load(f)


def main():
    # Ensure DB is ready
    migrate()

    config = load_config()
    services = config["managed_services"]

    watchers = [
        OllamaHealthWatcher(url="http://localhost:11434", timeout=5),
        DiskPressureWatcher(path="/" if __import__("sys").platform != "win32" else "C:\\"),
        MemoryPressureWatcher(),
        ServiceStatusWatcher(services=services),
    ]

    daemon = HermesDaemon(
        watchers=watchers,
        tick_seconds=10,
        dedup_repeat_seconds=300,
    )

    daemon.run_forever()


if __name__ == "__main__":
    main()