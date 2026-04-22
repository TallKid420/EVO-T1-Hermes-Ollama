"""
ChatWatcher — polls all configured chat sources for incoming user messages
and emits WatcherResult(event_type="user_message") into the daemon pipeline.

Sources:
  - Telegram (long-poll getUpdates)
  - Terminal (non-blocking stdin via queue thread)

Add new sources by implementing _poll_<source>() and appending to self._sources.
"""

import queue
import threading
import logging
from typing import Optional

import requests

from hermes.watchers.base import BaseWatcher, WatcherResult
from hermes.core.severity import Severity

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Terminal source — runs input() in a background thread so it's non-blocking
# ---------------------------------------------------------------------------

class _TerminalSource:
    """Reads stdin in a daemon thread and puts lines into a queue."""

    def __init__(self):
        self._q: queue.Queue[str] = queue.Queue()
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()

    def _read_loop(self):
        while True:
            try:
                line = input()          # blocks in its own thread — fine
                if line.strip():
                    self._q.put(line.strip())
            except EOFError:
                break                   # stdin closed (e.g. piped input)

    def drain(self) -> list[dict]:
        """Return all pending messages as dicts (non-blocking)."""
        messages = []
        while not self._q.empty():
            try:
                text = self._q.get_nowait()
                messages.append({
                    "source": "terminal",
                    "chat_id": "local",
                    "user_id": "local",
                    "text": text,
                    "message_id": None,
                })
            except queue.Empty:
                break
        return messages


# ---------------------------------------------------------------------------
# Telegram source — long-poll getUpdates
# ---------------------------------------------------------------------------

class _TelegramSource:
    """Polls Telegram Bot API for new messages."""

    def __init__(self, token: str, allowed_user_ids: list[int], timeout: int = 10):
        self._token = token
        self._allowed = set(allowed_user_ids)
        self._timeout = timeout
        self._offset: Optional[int] = None
        self._base = f"https://api.telegram.org/bot{token}"

    def drain(self) -> list[dict]:
        """Fetch pending updates, return filtered message dicts."""
        params: dict = {"timeout": self._timeout, "limit": 10}
        if self._offset is not None:
            params["offset"] = self._offset

        try:
            resp = requests.get(
                f"{self._base}/getUpdates",
                params=params,
                timeout=self._timeout + 5,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            log.warning("Telegram poll failed: %s", e)
            return []

        messages = []
        for update in data.get("result", []):
            self._offset = update["update_id"] + 1          # advance cursor
            msg = update.get("message") or update.get("edited_message")
            if not msg:
                continue
            user_id = msg.get("from", {}).get("id")
            if self._allowed and user_id not in self._allowed:
                log.debug("Ignoring message from unauthorized user %s", user_id)
                continue
            text = msg.get("text", "").strip()
            if not text:
                continue
            messages.append({
                "source": "telegram",
                "chat_id": msg["chat"]["id"],
                "user_id": user_id,
                "text": text,
                "message_id": msg["message_id"],
            })
        return messages


# ---------------------------------------------------------------------------
# ChatWatcher — the actual BaseWatcher implementation
# ---------------------------------------------------------------------------

class ChatWatcher(BaseWatcher):
    """
    Polls all active chat sources once per daemon tick.
    Returns the FIRST pending message found (one event per tick).
    Remaining messages are buffered and returned on subsequent ticks.
    """

    name = "chat"

    def __init__(self, cfg: dict):
        self._sources: list = []
        self._buffer: list[dict] = []

        # --- Terminal ---
        # Set True by Default
        self._sources.append(_TerminalSource())
        log.info("ChatWatcher: terminal source enabled")

        # --- SMS --- (placeholder for future implementation)

        # --- Gmail --- (placeholder for future implementation)

        # --- Telegram ---
        tg_cfg = cfg.get("telegram", {})
        if tg_cfg.get("input", False):
            token = tg_cfg.get("token")
            if not token:
                raise ValueError("ChatWatcher: telegram.token is required")
            allowed = tg_cfg.get("allowed_user_ids", [])
            self._sources.append(
                _TelegramSource(
                    token=token,
                    allowed_user_ids=allowed,
                    timeout=tg_cfg.get("poll_timeout", 10),
                )
            )
            log.info("ChatWatcher: telegram source enabled (allowed: %s)", allowed)

        if not self._sources:
            log.warning("ChatWatcher: no sources enabled — watcher will never trigger")

    def check(self) -> WatcherResult:
        """
        Called once per daemon tick.
        Drains all sources into buffer, pops one message, returns it as a WatcherResult.
        If nothing pending, returns triggered=False.
        """
        # Refill buffer from all sources
        for source in self._sources:
            self._buffer.extend(source.drain())

        if not self._buffer:
            return WatcherResult(
                triggered=False,
                severity=Severity.INFO,
                event_type="user_message",
                source="chat",
                message="",
                payload={},
            )

        msg = self._buffer.pop(0)
        log.debug("ChatWatcher: message from %s: %r", msg["source"], msg["text"])

        return WatcherResult(
            triggered=True,
            severity=Severity.INFO,
            event_type="user_message",
            source=msg["source"],
            message=msg["text"],
            payload=msg,           # full dict: source, chat_id, user_id, text, message_id
        )