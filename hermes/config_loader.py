from dataclasses import dataclass, field

import yaml
    
@dataclass
class AgentConfig:
    name: str
    type: str
    provider: str
    endpoint: str
    timeout_seconds: int
    temperature: int
    model: str
    system_prompt: str
    tools: list[str] = field(default_factory=list)
    schedule: str | None = None      # cron string, for scheduler type
    trigger: str | None = None       # event name, for event-driven
    enabled: bool = True

def load_config(path: str) -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f)

def load_agents(path: str) -> list[AgentConfig]:
    raw = load_config(path)
    agents = []
    for entry in raw.get("custom_agents", []).get("agents", []):
        if not entry.get("enabled", True):
            continue
        agents.append(AgentConfig(
            name=entry["name"],
            type=entry["type"],
            provider=entry["provider"],
            endpoint=entry.get("endpoint", "http://localhost:11434"),
            temperature=entry.get("temperature", 0),
            timeout_seconds=entry.get("timeout_seconds", 60),
            model=entry["model"],
            system_prompt=entry.get("system_prompt", ""),
            tools=entry.get("tools", []),
            schedule=entry.get("schedule"),
            trigger=entry.get("trigger"),
            enabled=entry.get("enabled", True),
        ))
    return agents