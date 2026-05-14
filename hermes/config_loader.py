"""
hermes/config_loader.py
"""
from __future__ import annotations
from config.manager import load
from dataclasses import dataclass, field
from typing import Any, Dict, Optional
import uuid


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
    extra: Dict[str, Any] = field(default_factory=dict)


def _agent_from_dict(entry: Dict[str, Any]) -> AgentConfig:
    """Build an AgentConfig from a raw yaml dict, pulling known fields and stashing the rest in extra."""
    known = {
        "name", "type", "provider", "endpoint", "timeout_seconds",
        "temperature", "model", "system_prompt", "tools",
        "schedule", "trigger", "enabled", "agent_id", "mailbox_id"
    }
    extra = {k: v for k, v in entry.items() if k not in known}

    if not entry.get("name"):
        raise ValueError("Agent config missing name")
    
    if entry.get("timeout_seconds", 0) <= 0:
        raise ValueError("timeout_seconds must be > 0")
    
    agent_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, entry["name"]))

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
        agent_id=agent_id,
        mailbox_id=agent_id,
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


def load_system_agents(path: str) -> list[AgentConfig]:
    raw = load(path)
    system = raw.get("system_agents", {})

    # Support both list-of-dicts and name-keyed dict formats
    if isinstance(system, list):
        entries = system
    elif isinstance(system, dict):
        agents_list = system.get("agents")
        if agents_list is not None:
            # { agents: [...] } format
            entries = agents_list
        else:
            # { name: {config}, name: {config} } flat dict format (wizard output)
            entries = [{"name": k, **v} for k, v in system.items()]
    else:
        entries = []

    return [
        _agent_from_dict(entry)
        for entry in entries
        if entry.get("enabled", True)
    ]


def load_custom_agents(path: str) -> list[AgentConfig]:
    """Load custom agents from config/agents.yaml."""
    raw = load(path)
    custom = raw.get("custom_agents", {})

    if isinstance(custom, list):
        entries = custom
    elif isinstance(custom, dict):
        agents_list = custom.get("agents")
        if agents_list is not None:
            entries = agents_list
        else:
            entries = [{"name": k, **v} for k, v in custom.items()]
    else:
        entries = []

    return [
        _agent_from_dict(entry)
        for entry in entries
        if entry.get("enabled", True)
    ]