from __future__ import annotations
import logging
import uuid
from datetime import datetime

from hermes.db.conn import connect
from hermes.config_loader import load_system_agents, load_custom_agents, AgentConfig
from hermes.agents.factory import AgentFactory
from hermes.agents.base_agent import BaseAgent

log = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = "config/agents.yaml"


class AgentSpawner:
    def __init__(self, config_path: str = DEFAULT_CONFIG_PATH):
        self._config_path = config_path
        self._system_agents: list[BaseAgent] = []
        self._custom_agents: list[BaseAgent] = []
        self._load_and_spawn()

    def _load_and_spawn(self):
        # System agents
        sys_configs = load_system_agents(self._config_path)
        log.info("AgentSpawner: loaded %d system agent config(s)", len(sys_configs))
        self._system_agents = AgentFactory.spawn_system(sys_configs)
        log.info(
            "AgentSpawner: spawned system agents: %s",
            [a.config.name for a in self._system_agents],
        )

        # Custom agents
        custom_configs = load_custom_agents(self._config_path)
        log.info("AgentSpawner: loaded %d custom agent config(s)", len(custom_configs))
        self._custom_agents = AgentFactory.spawn_system(custom_configs)  # same spawn logic
        log.info(
            "AgentSpawner: spawned custom agents: %s",
            [a.config.name for a in self._custom_agents],
        )

    def spawn_child_agent(self, parent: BaseAgent, config_override: dict) -> BaseAgent:
        if not parent.can_spawn_child():
            raise RuntimeError("Spawn limit exceeded for parent agent")

        child_config = parent.spawn_context(config_override)

        conn = connect()
        try:
            conn.execute(
                """
                INSERT INTO agent_nodes (
                    agent_id, parent_id, name, type,
                    spawn_depth, mailbox_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    child_config.agent_id,
                    parent.agent_id,
                    child_config.name,
                    child_config.type,
                    child_config.spawn_depth,
                    child_config.mailbox_id,
                    datetime.utcnow().isoformat(),
                ),
            )
            conn.commit()
        finally:
            conn.close()

        child_agent = AgentFactory.spawn(child_config)
        parent.children.append(child_config.agent_id)
        return child_agent

    # ── Lookups ───────────────────────────────────────────────────────────────

    def get_system_agents(self) -> list[BaseAgent]:
        return self._system_agents

    def get_custom_agents(self) -> list[BaseAgent]:
        return self._custom_agents

    def get_agent_by_name(self, name: str) -> BaseAgent | None:
        """Search system agents first, then custom agents."""
        for agent in self._system_agents:
            if agent.config.name.lower() == name.lower():
                return agent
        for agent in self._custom_agents:
            if agent.config.name.lower() == name.lower():
                return agent
        return None

    def reload(self):
        log.info("AgentSpawner: reloading all agents")
        AgentFactory._CACHE.clear()
        self._load_and_spawn()