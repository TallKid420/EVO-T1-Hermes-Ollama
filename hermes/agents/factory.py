# factory.py — totally valid
from hermes.agents.registry import AGENT_REGISTRY
from hermes.config_loader import load_agents, AgentConfig

configs = load_agents("config/agents.yaml")
print(configs)

class AgentFactory:
    def spawn(config):
        cls = AGENT_REGISTRY.get(config.type)
        if not cls:
            raise ValueError(f"Unknown agent type: {config.type}")
        return cls(config)
    
for config in configs:
    agent = AgentFactory.spawn(config)
    print(f"Spawned agent: {agent.config.name} of type {agent.config.type}")
    
# if __name__ == "__main__":
#     # test the factory
#     config = {"type": "chat"}
#     agent = AgentFactory.spawn(config)
#     print(agent.run())