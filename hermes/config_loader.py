"""
hermes/config_loader.py
"""
from __future__ import annotations
from config.manager import load
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class AgentConfig:
    name:            str
    type:            str
    provider:        str
    endpoint:        str
    timeout_seconds: int
    temperature:     float
    model:           str
    system_prompt:   str
    tools:           list[str]        = field(default_factory=list)
    schedule:        Optional[str]    = None   # cron string, for scheduler type
    trigger:         Optional[str]    = None   # event name, for event-driven
    enabled:         bool             = True

    # Not Yaml Defined
    agent_id: str | None = None
    mailbox_id: str | None = None
    parent_id: str | None = None
    spawn_depth: int = 0

    max_children: int = 5
    max_spawn_depth: int = 3

    # extra keys from yaml (policy, allowed_commands, etc.) stored here
    extra:           Dict[str, Any]


def _agent_from_dict(entry: Dict[str, Any]) -> AgentConfig:
    """Build an AgentConfig from a raw yaml dict, pulling known fields and stashing the rest in extra."""
    known = {
        "name", "type", "provider", "endpoint", "timeout_seconds",
        "temperature", "model", "system_prompt", "tools",
        "schedule", "trigger", "enabled",
    }
    extra = {k: v for k, v in entry.items() if k not in known}

    if not entry.get("name"):
        raise ValueError("Agent config missing name")
    
    if entry.get("timeout_seconds", 0) <= 0:
        raise ValueError("timeout_seconds must be > 0")

    return AgentConfig(
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
        extra=extra,
    )


def load_agents(path: str) -> list[AgentConfig]:
    """Load custom agents from config/agents.yaml."""
    raw = load(path)
    return [
        _agent_from_dict(entry)
        for entry in raw.get("custom_agents", {}).get("agents", [])
        if entry.get("enabled", True)
    ]
    # agents = []
    # for entry in raw.get("custom_agents", {}).get("agents", []):
    #     if not entry.get("enabled", True):
    #         continue
    #     agents.append(_agent_from_dict(entry))
    # return agents


def load_system_agents(path: str) -> list[AgentConfig]:
    raw = load(path)
    return [
        _agent_from_dict(entry)
        for entry in raw.get("system_agents", {}).get("agents", [])
        if entry.get("enabled", True)
    ]
    # agents = []
    # for entry in raw.get("system_agents", {}).get("agents", []):
    #     if not entry.get("enabled", True):
    #         continue
    #     agents.append(_agent_from_dict(entry))
    # return agents

# # Quick test of loading agents
# agents = load_system_agents("config/agents.yaml")
# print(f"Loaded {len(agents)} system agents from config/agents.yaml:")
# for agent in agents:
#     print(f"Loaded agent config: {agent}")