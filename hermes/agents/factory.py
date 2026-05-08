"""
hermes/agents/factory.py
"""
from __future__ import annotations
from typing import Optional
from hermes.agents.registry import AGENT_REGISTRY
from hermes.config_loader import AgentConfig


class AgentFactory:
    @staticmethod
    def spawn(config: AgentConfig):
        """Instantiate an agent from an AgentConfig."""
        print(f"Config: {config}")
        cls = AGENT_REGISTRY.get(config.type)
        if not cls:
            raise ValueError(
                f"Unknown agent type: '{config.type}'. "
                f"Registered types: {list(AGENT_REGISTRY.keys())}"
            )
        return cls(config)

    @classmethod
    def spawn_all_custom(cls, config_path: Optional[str] = None) -> list:
        """Load and spawn all enabled custom agents."""
        path    = config_path or cls.CONFIG_PATH
        configs = load_agents(path)
        agents  = []
        for config in configs:
            try:
                agent = cls.spawn(config)
                agents.append(agent)
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(
                    "Failed to spawn custom agent '%s': %s", config.name, e
                )
        return agents
    
# for config in configs:
#     agent = AgentFactory.spawn(config)
#     print(f"Spawned agent: {agent.config.name} of type {agent.config.type}")
    
# # if __name__ == "__main__":
# #     # test the factory
# #     config = {"type": "chat"}
# #     agent = AgentFactory.spawn(config)
# #     print(agent.run())