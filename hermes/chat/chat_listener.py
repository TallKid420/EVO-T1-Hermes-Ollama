from hermes.plugins.communication.telegram import TelegramCommunicationPlugin
from hermes.plugins.provider.llm_provider import ChatProvider
from typing import Dict, Any
import yaml

def load_config(path: str) -> Dict[str, Any]:
    with open(path, "r") as f:
        return yaml.safe_load(f) or {}
    
mapping = {
    "telegram": TelegramCommunicationPlugin,
    "gmail": None,
    "sms": None,
}

class ChatListener:
    def __init__(self, plugincfg: Dict[str, Any] | None, agentcfg: Dict[str, Any] | None):
        self.plugincfg = plugincfg or load_config("config/plugins.yaml")
        self.agentcfg = agentcfg or load_config("config/agents.yaml")
        active = self.plugincfg.get("active", {}).get("communication")
        if not isinstance(active, dict):
            raise ValueError("Missing or invalid notification config key: active.communication")
        self.notifiers = {}
        for name, settings in active.items():
            cls = mapping.get(name)
            if settings.get("input") and cls is not None:
                self.notifiers[name] = cls(
                    self.plugincfg.get("plugins", {}).get(name, {})
                )

    def heartbeat(self):
        return

    def router(self, message: str):
        router_cfg = self.agentcfg.get("system_agents", {}).get("router", {})
        custom_agents_cfg = self.agentcfg.get("custom_agents", {})
        custom_agent_names = next(
            (g.get("agents", []) for g in self.agentcfg.get("groups", []) if g.get("name") == "custom_agents"),
            [],
        )
        agent_lines = "\n".join(
            f"- {name}: {custom_agents_cfg.get(name, {}).get('description') or custom_agents_cfg.get(name, {}).get('system_prompt') or 'No description available.'}"
            for name in custom_agent_names
        )
        prompt = f"""You are the Hermes Router Agent. Your only job is to read the user's message and decide which agent should handle it.

## Available Agents
{agent_lines}

## Rules
1. Choose exactly one agent from the list above.
2. Pick the agent whose description best matches the intent of the user's message.
3. Never explain your reasoning. Return JSON only.

## User Message
{message}

## Output Format (strict JSON, no extra keys, no markdown)
{{"agent": "agent_name"}}"""
        response = ChatProvider().send_system_message(
            prompt=prompt,
            cfg=router_cfg,
            format="json",
            stream=False,
        )
        return response
