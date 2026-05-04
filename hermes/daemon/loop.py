import time
import logging
import threading
from typing import List
import yaml

from hermes.watchers.base import BaseWatcher
from hermes.daemon.state import WatcherState
from hermes.db import store
from hermes.db.worker import run_once
from hermes.chat.message_handler import handle_user_message
from hermes.plugins.communication.notifications.handler import NotificationHandler


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
        self._lock = threading.Lock()  # protects _running and config reloads

    def reload_config(self) -> None:
        """Reload plugins.yaml and agents.yaml in place. Thread-safe."""
        try:
            new_plugins = _load_yaml_config("config/plugins.yaml")
            new_agents  = _load_yaml_config("config/agents.yaml")
            with self._lock:
                self.plugins_cfg = new_plugins
                self.agents_cfg  = new_agents
            logger.info("CONFIG hot-reloaded: plugins.yaml and agents.yaml")
        except Exception:
            logger.exception("CONFIG reload failed — keeping previous config")

    def _run_watchers(self) -> int:
        emitted = 0
        for watcher in self.watchers:
            try:
                result = watcher.check()

                # User messages are handled separately — skip normal event flow
                if result.triggered and result.event_type == "user_message":
                    with self._lock:
                        plugins_cfg = self.plugins_cfg
                        agents_cfg  = self.agents_cfg
                    handle_user_message(result, plugins_cfg, agents_cfg)
                    continue

                if self.state.should_emit(result, self.dedup_repeat_seconds):
                    # Always persist the event to the DB
                    store.add_event(
                        severity=result.severity,
                        source=result.source,
                        type_=result.event_type,
                        message=result.message,
                        payload=result.payload,
                    )
                    emitted += 1

                    if result.triggered:
                        # Active alert — log with severity and notify
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
                        # State recovered — log as info only
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
        with self._lock:
            self._running = True
        logger.info("Hermes daemon started. Tick every %ss", self.tick_seconds)
        while self._running:
            try:
                self.tick()
            except KeyboardInterrupt:
                logger.info("Hermes daemon shutting down")
                with self._lock:
                    self._running = False
                break
            except Exception:
                logger.exception("Unhandled exception in tick")
            time.sleep(self.tick_seconds)

    def run_once(self):
        """Single tick — useful for testing."""
        self.tick()