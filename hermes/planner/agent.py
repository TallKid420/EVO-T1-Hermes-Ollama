import json
import requests
import yaml
from typing import Dict, Any
from hermes.provider.chat import ChatProvider


def load_planner_config(path: str = "config/agents.yaml") -> Dict[str, Any]:
    try:
        with open(path, "r") as f:
            data = yaml.safe_load(f) or {}
            return data.get("system_agents", {}).get("planner", {})
    except FileNotFoundError:
        return {}


class Planner:
    def __init__(self, config_path: str = "config/agents.yaml"):
        cfg = load_planner_config(config_path)

        self.model = cfg.get("model")
        self.provider = cfg.get("provider")
        self.endpoint = cfg.get("endpoint")
        self.timeout_seconds = int(cfg.get("timeout_seconds"))
        self.allowed_actions = cfg.get("allowed_actions")
        self.rules = cfg.get("rules")
        self.cfg = cfg

    def plan(self, event: Dict[str, Any], system_status: Dict[str, Any]) -> Dict[str, Any]:
        allowed_actions_text = ", ".join(self.allowed_actions)
        rules_text = "\n".join(f"{idx}. {rule}" for idx, rule in enumerate(self.rules, start=1))

        prompt = f"""
### Task
You are the Hermes Planner Agent for a GMKtec EVO-T1 server. 
An event has occurred. Decide the best course of action.

### Context
Event: {event['message']}
Severity: {event['severity']}
System Status: {json.dumps(system_status)}

### Rules
1. Only recommend actions from: [{allowed_actions_text}]
{rules_text}
"""
        _format = """
        {
            "action": "string",
            "reasoning": "string",
            "risk_score": 1-10
        }
        """

        return ChatProvider().send_message(
            prompt=prompt, 
            cfg=self.cfg, 
            format=_format, 
            stream=False
        )