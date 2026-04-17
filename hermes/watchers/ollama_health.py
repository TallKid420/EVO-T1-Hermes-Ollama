import urllib.request
import urllib.error

from hermes.core.severity import Severity
from hermes.watchers.base import BaseWatcher, WatcherResult


class OllamaHealthWatcher(BaseWatcher):
    name = "ollama_health"

    def __init__(
        self,
        url: str = "http://localhost:11434",
        timeout: int = 5,
    ):
        self.url = url
        self.timeout = timeout

    def check(self) -> WatcherResult:
        try:
            req = urllib.request.urlopen(self.url, timeout=self.timeout)
            healthy = req.status == 200
        except Exception:
            healthy = False

        if healthy:
            return WatcherResult(
                triggered=False,
                severity=Severity.INFO,
                event_type="ollama_health",
                source="ollama_health_watcher",
                message="Ollama is healthy",
                payload={"url": self.url, "healthy": True},
            )

        return WatcherResult(
            triggered=True,
            severity=Severity.CRITICAL,
            event_type="service_unhealthy",
            source="ollama_health_watcher",
            message="Ollama health check failed",
            payload={"url": self.url, "healthy": False, "service": "ollama"},
        )