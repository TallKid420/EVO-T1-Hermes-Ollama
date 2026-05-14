"""
hermes/agents/factory.py
"""
from __future__ import annotations
from hermes.agents.registry import AGENT_REGISTRY
from hermes.config_loader import AgentConfig

import logging
import uuid

log = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = "agents.yaml"

class AgentFactory:

    _CACHE = {}
    
    @staticmethod
    def spawn(config: AgentConfig):
        key = config.agent_id

        if key in AgentFactory._CACHE:
            return AgentFactory._CACHE[key]
        
        cls = AGENT_REGISTRY.get(config.type)

        if not cls:
            raise ValueError(
                f"Unknown agent type: '{config.type}'. "
                f"Registered types: {list(AGENT_REGISTRY.keys())}"
            )
        
        agent = cls(config)

        AgentFactory._CACHE[key] = agent

        return agent

    @classmethod
    def spawn_system(cls, configs: list[AgentConfig]) -> list:
        agents  = []
        for config in configs:
            try:
                agents.append(cls.spawn(config))
            except Exception as e:
                log.error("Failed to spawn custom agent '%s': %s", config.name, e)
        return agents

    @classmethod
    def spawn_custom(cls, configs: list[AgentConfig]) -> list:
        agents  = []
        for config in configs:
            try:
                agents.append(cls.spawn(config))
            except Exception as e:
                log.error("Failed to spawn custom agent '%s': %s", config.name, e)
        return agents