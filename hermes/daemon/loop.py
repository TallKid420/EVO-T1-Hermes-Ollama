import time
import logging
import threading
from typing import List
import yaml

from hermes.watchers.base import BaseWatcher
from hermes.daemon.state import WatcherState
from hermes.db import store
from hermes.db.worker import run_once
from hermes.plugins.communication.notifications.handler import NotificationHandler
from hermes.plugins.communication.telegram import TelegramCommunicationPlugin
from hermes.runtime.spawner import AgentSpawner
from hermes.chat.orchestrator import Orchestrator


logger = logging.getLogger(__name__)


def _extract_assistant_text(result) -> str:
    if isinstance(result, dict):
        if result.get("error"):
            return str(result.get("message") or "Agent execution failed")
        messages = result.get("messages")
        if isinstance(messages, list) and messages:
            last = messages[-1]
            content = getattr(last, "content", None)
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                return "\n".join(str(part) for part in content)
    return str(result)


def _send_user_reply(source: str, chat_id, text: str, plugins_cfg: dict) -> None:
    if source == "terminal":
        print(f"\n[Hermes] {text}\n")
        return
    if source == "telegram":
        try:
            tg_cfg = dict((plugins_cfg or {}).get("plugins", {}).get("telegram", {}))
            if chat_id is not None:
                tg_cfg["chat_id"] = str(chat_id)
            TelegramCommunicationPlugin(tg_cfg).send(text)
        except Exception:
            logger.exception("Telegram reply failed")
        return
    logger.warning("Unknown chat source '%s' - cannot reply", source)


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
        self.spawner = AgentSpawner(config_path="config/agents.yaml")
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
                self.spawner.reload()
            logger.info("CONFIG hot-reloaded: plugins.yaml and agents.yaml")
        except Exception:
            logger.exception("CONFIG reload failed — keeping previous config")

    def _run_watchers(self) -> int:
        emitted = 0
        for watcher in self.watchers:
            try:
                result = watcher.check()

                if result.triggered and result.event_type == "user_message":
                    payload = result.payload or {}
                    source = payload.get("source")
                    chat_id = payload.get("chat_id")
                    text = payload.get("text") or result.message
                    agent_name = payload.get("agent") or "server"
                    if not text:
                        continue
                    with self._lock:
                        plugins_cfg = self.plugins_cfg
                        agent = self.spawner.get_agent_by_name(agent_name)
                    if not agent:
                        _send_user_reply(source, chat_id, f"Agent '{agent_name}' not found.", plugins_cfg)
                        continue
                    try:
                        response = Orchestrator(agent).run(text)
                        _send_user_reply(source, chat_id, _extract_assistant_text(response), plugins_cfg)
                    except Exception:
                        logger.exception("Failed to process user message with agent '%s'", agent_name)
                        _send_user_reply(source, chat_id, "Agent error while processing message.", plugins_cfg)
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