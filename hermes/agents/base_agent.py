from abc import ABC, abstractmethod
from hermes.config_loader import AgentConfig
from typing import Any, Optional

import logging
import uuid
import copy

class BaseAgent(ABC):
    def __init__(self, config: AgentConfig):
        self.config = config        # stores the YAML config for this agent
        self.running = False        # used later for run_loop()
        self._runtime = None
        
        self.agent_id = config.agent_id or str(uuid.uuid4())
        config.agent_id = self.agent_id
        self.mailbox_id = config.mailbox_id or self.agent_id
        config.mailbox_id = self.mailbox_id

        self.parent_id = config.parent_id
        self.spawn_depth = config.spawn_depth
        self.children: list[str] = []

    def can_spawn_child(self) -> bool:
        if (self.spawn_depth < self.config.max_spawn_depth 
            and len(self.children) < self.config.max_children):
            return True
        else:
            return False
        
    def spawn_context(self, overrides: dict | None = None) -> AgentConfig:
        overrides = overrides or {}

        if not self.agent_id:
            raise ValueError("Agent ID Not Set")
        
        base = copy.deepcopy(self.config)

        base.agent_id = str(uuid.uuid4())
        base.parent_id = self.agent_id
        base.spawn_depth = self.spawn_depth + 1
        base.mailbox_id = base.agent_id

        _RESERVED = {
            "agent_id",
            "mailbox_id",
            "parent_id",
            "spawn_depth",
        }

        for k, v in overrides.items():
            if k in _RESERVED:
                continue
            setattr(base, k, v)

        return base
    
    def send_task(self, target_agent_id: str, payload: dict):
        raise NotImplementedError("Send Task not implamented yet...")
    
    def fetch_mailbox(self):
        raise NotImplementedError("Fetch Mailbox not implamented yet...")

    def get_runtime(self):
        if self._runtime is None:
            self._runtime = self._build_runtime()

        return self._runtime
    
    @staticmethod
    def log(value: Any, level: str = "info"):
        logger = logging.getLogger(__name__)
        getattr(logger, level, logger.info)(value)
    
    @abstractmethod
    def _build_runtime(self):
        pass

    @abstractmethod
    def run(self, input=None):
        pass                        # every agent MUST implement this

    def run_loop(self):
        pass                        # optional — autonomous agents override this