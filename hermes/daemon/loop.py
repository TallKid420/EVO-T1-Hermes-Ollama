import time
import logging
from typing import List
import yaml

from hermes.watchers.base import BaseWatcher
from hermes.daemon.state import WatcherState
from hermes.db import store
from hermes.db.worker import run_once
from hermes.chat.message_handler import handle_user_message
from hermes.notifications.handler import NotificationHandler


logger = logging.getLogger(__name__)


def _load_yaml_config(path: str):
    with open(path, "r") as f:
        return yaml.safe_load(f) or {}


def _severity_name(severity) -> str:
    value = getattr(severity, "value", severity)
    return str(value).strip().lower()


def _log_event_with_severity(source: str, message: str, severity) -> None:
    sev = _severity_name(severity)
    line = "EVENT %s | %s | %s"
    if sev == "critical":
        logger.critical(line, sev.upper(), source, message)
    elif sev == "warning":
        logger.warning(line, sev.upper(), source, message)
    else:
        logger.info(line, sev.upper(), source, message)


class HermesDaemon:
    def __init__(
        self,
        watchers: List[BaseWatcher],
        tick_seconds: int = 10,
        dedup_repeat_seconds: int = 300,
    ):
        self.watchers = watchers
        self.tick_seconds = tick_seconds
        self.dedup_repeat_seconds = dedup_repeat_seconds
        self.state = WatcherState()
        self.notification_handler = NotificationHandler()
        self.plugins_cfg = _load_yaml_config("config/plugins.yaml")
        self.agents_cfg = _load_yaml_config("config/agents.yaml")
        self._running = False

    def reload_config(self) -> None:
        """Reload plugins.yaml and agents.yaml in place. Thread-safe for read-heavy use."""
        try:
            self.plugins_cfg = _load_yaml_config("config/plugins.yaml")
            self.agents_cfg = _load_yaml_config("config/agents.yaml")
            logger.info("CONFIG hot-reloaded: plugins.yaml and agents.yaml")
        except Exception:
            logger.exception("CONFIG reload failed — keeping previous config")

    def _run_watchers(self) -> int:
        emitted = 0
        for watcher in self.watchers:
            try:
                result = watcher.check()
                if result.triggered and result.event_type == "user_message":
                    handle_user_message(result, self.plugins_cfg, self.agents_cfg)
                    continue
                if self.state.should_emit(result, self.dedup_repeat_seconds):
                    if result.triggered:

                        store.add_event(
                            severity=result.severity,
                            source=result.source,
                            type_=result.event_type,
                            message=result.message,
                            payload=result.payload,
                        )
                        emitted += 1
                        _log_event_with_severity(
                            source=result.source,
                            message=result.message,
                            severity=result.severity,
                        )
                        self.notification_handler.send_notification(
                            f"{result.source}\n{result.message}",
                            severity=result.severity,
                        )
                    else:
                        # State recovered — log as info
                        logger.info("OK %s | %s", result.source, result.message)
            except Exception:
                logger.exception("Watcher %s raised an exception", watcher.name)
        return emitted

    def tick(self):
        emitted = self._run_watchers()
        result = run_once()
        logger.info(
            "TICK events_emitted=%s tasks_created=%s tasks_ran=%s",
            emitted,
            result["tasks_created"],
            result["tasks_ran"],
        )

    def run_forever(self):
        self._running = True
        logger.info("Hermes daemon started. Tick every %ss", self.tick_seconds)
        while self._running:
            try:
                self.tick()
            except KeyboardInterrupt:
                logger.info("Hermes daemon shutting down")
                self._running = False
                break
            except Exception:
                logger.exception("Unhandled exception in tick")
            time.sleep(self.tick_seconds)

    def run_once(self):
        """Single tick — useful for testing."""
        self.tick()