from datetime import datetime, timedelta
from collections import defaultdict


class CooldownManager:
    def __init__(self):
        self.last_actions = {}
        self.action_history = defaultdict(list)

    def _now(self):
        return datetime.utcnow()

    def record(self, key: str):
        now = self._now()
        self.last_actions[key] = now
        self.action_history[key].append(now)

    def can_execute(self, key: str, cooldown_seconds: int) -> bool:
        last = self.last_actions.get(key)
        if not last:
            return True
        return (self._now() - last).total_seconds() >= cooldown_seconds

    def count_recent(self, key: str, window_seconds: int) -> int:
        now = self._now()
        window_start = now - timedelta(seconds=window_seconds)

        self.action_history[key] = [
            t for t in self.action_history[key] if t > window_start
        ]

        return len(self.action_history[key])

    def circuit_breaker_triggered(self, key: str, max_failures: int, window_seconds: int) -> bool:
        return self.count_recent(key, window_seconds) >= max_failures