import time
import traceback
from typing import List

from hermes.watchers.base import BaseWatcher
from hermes.daemon.state import WatcherState
from hermes.db import store
from hermes.db.worker import run_once
from hermes.notifications.telegram import send


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
        self._running = False

    def _run_watchers(self) -> int:
        emitted = 0
        for watcher in self.watchers:
            try:
                result = watcher.check()
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
                        print(
                            f"[EVENT] {result.severity} | {result.source} | {result.message}"
                        )
                        send(f"{result.source}\n{result.message}", severity=result.severity)
                    else:
                        # State recovered — log as info
                        print(f"[OK]    {result.source} | {result.message}")
            except Exception:
                print(f"[ERROR] Watcher {watcher.name} raised an exception:")
                traceback.print_exc()
        return emitted

    def tick(self):
        emitted = self._run_watchers()
        result = run_once()
        print(
            f"[TICK]  events_emitted={emitted} "
            f"tasks_created={result['tasks_created']} "
            f"tasks_ran={result['tasks_ran']}"
        )

    def run_forever(self):
        self._running = True
        print(f"[HERMES] Daemon started. Tick every {self.tick_seconds}s.")
        while self._running:
            try:
                self.tick()
            except KeyboardInterrupt:
                print("[HERMES] Shutting down.")
                self._running = False
                break
            except Exception:
                print("[HERMES] Unhandled exception in tick:")
                traceback.print_exc()
            time.sleep(self.tick_seconds)

    def run_once(self):
        """Single tick — useful for testing."""
        self.tick()