"""
hermes/agents/factory.py
"""
from __future__ import annotations
from typing import Optional
from config.manager import load
from hermes.agents.registry import AGENT_REGISTRY
from hermes.config_loader import AgentConfig

import logging

log = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = "agents.yaml"

class AgentFactory:

    _CACHE = {}
    
    @staticmethod
    def spawn(config: AgentConfig):
        key = config.name

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
    def spawn_all_custom(cls, config_path: Optional[str] = None) -> list:
        """Load and spawn all enabled custom agents."""
        path = config_path or DEFAULT_CONFIG_PATH
        configs = load(path)
        agents  = []
        for config in configs:
            try:
                agents.append(cls.spawn(config))
            except Exception as e:
                log.error("Failed to spawn custom agent '%s': %s", config.name, e)
        return agents
    
# for config in configs:
#     agent = AgentFactory.spawn(config)
#     print(f"Spawned agent: {agent.config.name} of type {agent.config.type}")
    
# # if __name__ == "__main__":
# #     # test the factory
# #     config = {"type": "chat"}
# #     agent = AgentFactory.spawn(config)
# #     print(agent.run())