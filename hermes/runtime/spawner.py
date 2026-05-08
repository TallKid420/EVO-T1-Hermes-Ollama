from __future__ import annotations
import logging

from hermes.config_loader import load_system_agents
from hermes.agents.factory import AgentFactory
from hermes.agents.base_agent import BaseAgent

log = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = "config/agents.yaml"


class AgentSpawner:
    def __init__(self, config_path: str = DEFAULT_CONFIG_PATH):
        self._config_path = config_path
        self._server_agents: list[BaseAgent] = []
        self._load_and_spawn()

    def _load_and_spawn(self):
        print("Load and Spawn Ran")
        configs = load_system_agents(self._config_path)  # ← returns list[AgentConfig]
        print(f"Loaded {len(configs)} system agent config(s)")
        self._server_agents = AgentFactory.spawn_system(configs)
        print(f"Spawned agents: {self._server_agents}")
        log.info(
            "AgentSpawner: spawned %d system agent(s): %s",
            len(self._server_agents),
            [a.config.name for a in self._server_agents],
        )

    def get_server_agents(self) -> list[BaseAgent]:
        return self._server_agents

    def get_agent_by_name(self, name: str) -> BaseAgent | None:
        for agent in self._server_agents:
            if agent.config.name == name:
                return agent
        return None

    def reload(self):
        log.info("AgentSpawner: reloading system agents")
        self._load_and_spawn()