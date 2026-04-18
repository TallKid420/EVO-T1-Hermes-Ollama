from abc import ABC, abstractmethod
from typing import Any, Dict, List


class HermesPlugin(ABC):
    """Base interface for always-on Hermes plugins."""

    name: str = "unnamed_plugin"
    description: str = "No description provided."
    required_permissions: List[str] = []

    def __init__(self) -> None:
        self.config: Dict[str, Any] = {}

    def initialize(self, config: Dict[str, Any]) -> None:
        self.config = config or {}

    @abstractmethod
    def execute(self, **kwargs: Any) -> Any:
        raise NotImplementedError

    def shutdown(self) -> None:
        return None
