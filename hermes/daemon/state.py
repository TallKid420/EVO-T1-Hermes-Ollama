from typing import Dict, Optional
from datetime import datetime

from hermes.watchers.base import WatcherResult
from hermes.core.severity import Severity


class WatcherState:
    """
    Tracks the last known state per watcher.
    Only signals a new event when state changes.
    """

    def __init__(self):
        # key: watcher name → last WatcherResult
        self._last: Dict[str, WatcherResult] = {}
        self._last_event_time: Dict[str, datetime] = {}

    def should_emit(self, result: WatcherResult, min_repeat_seconds: int = 300) -> bool:
        """
        Returns True if this result represents a state change
        OR if the same triggered state has persisted beyond min_repeat_seconds
        (so you still get reminded of ongoing issues).
        """
        key = result.source
        last = self._last.get(key)

        # First time seeing this watcher
        if last is None:
            self._last[key] = result
            self._last_event_time[key] = datetime.utcnow()
            return result.triggered

        # State changed (triggered → not triggered, or severity changed)
        state_changed = (last.triggered != result.triggered) or (last.severity != result.severity)

        if state_changed:
            self._last[key] = result
            self._last_event_time[key] = datetime.utcnow()
            return True

        # Still triggered — re-emit if it's been a while (ongoing alert reminder)
        if result.triggered:
            last_time = self._last_event_time.get(key, datetime.utcnow())
            elapsed = (datetime.utcnow() - last_time).total_seconds()
            if elapsed >= min_repeat_seconds:
                self._last_event_time[key] = datetime.utcnow()
                return True

        return False

    def update(self, result: WatcherResult):
        self._last[result.source] = result