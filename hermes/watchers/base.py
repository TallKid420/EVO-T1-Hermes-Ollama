from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Dict, Any

from hermes.core.severity import Severity


@dataclass
class WatcherResult:
    triggered: bool
    severity: Severity
    event_type: str
    source: str
    message: str
    payload: Dict[str, Any]


class BaseWatcher(ABC):
    name: str = "base"

    @abstractmethod
    def check(self) -> WatcherResult:
        """Run one check cycle. Always returns a WatcherResult."""
        ...