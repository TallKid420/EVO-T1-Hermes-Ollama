import json
import yaml
from typing import Dict, Any, Optional, List
from langchain_ollama import ChatOllama


def load_planner_config(path: str = "config/agents.yaml") -> Dict[str, Any]:
    with open(path, "r") as f:
        data = yaml.safe_load(f) or {}
    planner_cfg = data.get("system_agents", {}).get("planner")
    if not isinstance(planner_cfg, dict):
        raise ValueError("Missing required planner config at system_agents.planner")
    return planner_cfg


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
        required_fields = [
            "max_history", "model", "provider", "endpoint",
            "timeout_seconds", "allowed_actions", "rules",
        ]
        missing = [f for f in required_fields if f not in cfg]
        if missing:
            raise ValueError(f"Missing required planner config field(s): {missing}")

        self.max_history      = int(cfg["max_history"])
        self.model            = str(cfg["model"])
        self.provider         = str(cfg["provider"])
        self.endpoint         = str(cfg["endpoint"])
        self.timeout_seconds  = int(cfg["timeout_seconds"])
        self.allowed_actions  = list(cfg["allowed_actions"])
        self.rules            = list(cfg["rules"])
        self.cfg              = cfg

        if not self.allowed_actions:
            raise ValueError("planner.allowed_actions cannot be empty")
        if not self.rules:
            raise ValueError("planner.rules cannot be empty")

        # Build LLM once — reused on every plan() call
        self._llm = ChatOllama(
            model=self.model,
            base_url=self.endpoint,
            temperature=0,          # deterministic plans
            timeout=self.timeout_seconds,
        )

    def _normalize_plan(self, raw_plan: Dict[str, Any], event_message: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        plan = dict(raw_plan)
        if not isinstance(plan.get("action_args"), dict):
            plan["action_args"] = {}
        plan["requires_approval"] = bool(plan.get("requires_approval", False))
        plan["reasoning"] = str(plan.get("reasoning", ""))

        try:
            plan["risk_score"] = int(plan.get("risk_score", 5))
        except (TypeError, ValueError):
            plan["risk_score"] = 5
        plan["risk_score"] = max(1, min(10, plan["risk_score"]))

        if plan.get("action") not in self.allowed_actions:
            plan["action"] = "send_notification"
            plan["action_args"] = {"message": f"Planner chose invalid action. Event: {event_message}"}
            plan["reasoning"] = "Safety: invalid action replaced with notification."

        if plan.get("action") == "restart_service" and not plan.get("action_args", {}).get("service"):
            svc = payload.get("service")
            if svc:
                plan["action_args"] = {"service": svc}
            else:
                plan["action"] = "send_notification"
                plan["action_args"] = {
                    "message": f"restart_service planned but no service name found. Event: {event_message}"
                }

        if plan.get("action") == "delete_files":
            plan["requires_approval"] = True

        return plan

    def plan(
        self,
        event: Dict[str, Any],
        system_status: Dict[str, Any],
        action_history: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        action_history = action_history or []
        event_type = event.get("type", "")
        payload    = event.get("payload", {})

        # --- Survival layer ---
        if event_type in SURVIVAL_OVERRIDES:
            override = SURVIVAL_OVERRIDES[event_type](payload)
            if override.get("action") == "restart_service":
                if override["action_args"].get("service"):
                    return override

        # --- LLM layer ---
        allowed_actions_text = ", ".join(self.allowed_actions)
        rules_text = "\n".join(
            f"{i}. {rule}" for i, rule in enumerate(self.rules, start=1)
        )
        history_text = "None" if not action_history else "\n".join(
            f"- [{h['timestamp']}] Action: {h['action']} → Result: {h['result']}"
            for h in action_history[-self.max_history:]
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

### Recent Action History
{history_text}

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
            response = self._llm.invoke(prompt)
            raw_plan = json.loads(response.content)
            if not isinstance(raw_plan, dict):
                raise ValueError(f"Planner returned non-dict: {type(raw_plan).__name__}")
            return self._normalize_plan(raw_plan, event.get("message", ""), payload)

        except Exception as e:
            return {
                "action": "send_notification",
                "action_args": {"message": f"Planner LLM failed: {e}. Event: {event.get('message')}"},
                "requires_approval": False,
                "reasoning": "LLM unavailable, notifying operator.",
                "risk_score": 1,
                "_fallback": True,
            }