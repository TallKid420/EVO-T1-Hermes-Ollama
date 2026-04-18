import json
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


# Survival reflexes — LLM is NOT consulted for these.
# These are "brainstem" rules: if the system can't heal itself, nothing else matters.
SURVIVAL_OVERRIDES = {
    "service_unhealthy": lambda payload: {
        "action": "restart_service",
        "action_args": {"service": payload.get("service")},
        "requires_approval": False,
        "reasoning": "Survival reflex: service is down, restart immediately.",
        "risk_score": 2,
        "_override": True,
    }
}


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
        event_type = event.get("type", "")
        payload = event.get("payload", {})

        # --- Survival layer (brainstem) ---
        # Only fires when the system MUST act to stay alive.
        # LLM is bypassed entirely for these.
        if event_type in SURVIVAL_OVERRIDES:
            override = SURVIVAL_OVERRIDES[event_type](payload)
            # Validate the override has required args before returning
            if override.get("action") == "restart_service":
                if not override["action_args"].get("service"):
                    # No service name = can't act, fall through to LLM
                    pass
                else:
                    return override

        # --- LLM layer (brain) ---
        # Everything else goes to the Planner model.
        allowed_actions_text = ", ".join(self.allowed_actions)
        rules_text = "\n".join(
            f"{idx}. {rule}" for idx, rule in enumerate(self.rules, start=1)
        )

        prompt = f"""
### Task
You are the Hermes Planner Agent for a GMKtec EVO-T1 Ubuntu server.
An event has occurred. Decide the best course of action.
Return a SINGLE valid JSON object only. No explanation outside the JSON.

### Event
event_type: {event_type}
severity: {event.get("severity")}
message: {event.get("message")}
payload: {json.dumps(payload)}

### System Status
{json.dumps(system_status)}

### Rules
1. Only recommend actions from: [{allowed_actions_text}]
{rules_text}

### Output (exact JSON schema, no extra keys)
{{
  "action": "one of [{allowed_actions_text}]",
  "action_args": {{}},
  "requires_approval": false,
  "reasoning": "short explanation",
  "risk_score": 1
}}
"""

        try:
            plan = ChatProvider().send_message(
                prompt=prompt,
                cfg=self.cfg,
                format="json",
                stream=False,
            )
        except Exception as e:
            # LLM failed — fall back to notify so at least you know
            return {
                "action": "send_notification",
                "action_args": {"message": f"Planner LLM failed: {e}. Event: {event.get('message')}"},
                "requires_approval": False,
                "reasoning": "LLM unavailable, notifying operator.",
                "risk_score": 1,
                "_fallback": True,
            }

        # --- Safety layer (laws of reality) ---
        # Enforce invariants the LLM must not violate.
        # Not logic — just constraints.

        # 1. action must be in allowlist
        if plan.get("action") not in self.allowed_actions:
            plan["action"] = "send_notification"
            plan["action_args"] = {"message": f"Planner chose invalid action. Event: {event.get('message')}"}
            plan["reasoning"] = "Safety: invalid action replaced with notification."

        # 2. restart_service must always have a service name
        if plan.get("action") == "restart_service":
            if not plan.get("action_args", {}).get("service"):
                svc = payload.get("service")
                if svc:
                    plan["action_args"] = {"service": svc}
                else:
                    plan["action"] = "send_notification"
                    plan["action_args"] = {"message": f"restart_service planned but no service name found. Event: {event.get('message')}"}

        # 3. delete_files must always require approval
        if plan.get("action") == "delete_files":
            plan["requires_approval"] = True

        return plan