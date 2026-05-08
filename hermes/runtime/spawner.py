from hermes.config_loader import load_system_agents
from hermes.agents.factory import AgentFactory
from hermes.agents.base_agent import BaseAgent

class AgentSpawner:
    def __init__(self):
        self._server_agents = []
        self.server_agents_cfg = load_system_agents("config/agents.yaml")

        # for agent in self.server_agents_cfg:
        #     self._server_agents.append(agent)

    def get_server_agents(self):
        return self.server_agents_cfg