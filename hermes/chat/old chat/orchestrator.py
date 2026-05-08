"""
hermes/executor/orchestrator.py

The primary orchestrator agent.
terminal.py calls orchestrator.run(user_message) and prints the result.
"""

from __future__ import annotations

import logging
import yaml
from typing import Any, Dict

from hermes.executor.toolhandler import ToolLogger
from hermes.executor.search_tools import SearchTools

log = logging.getLogger(__name__)


def _load_yaml(path: str) -> Dict[str, Any]:
    try:
        with open(path, "r") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        log.warning("Config file not found: %s", path)
        return {}


class Orchestrator:
    """
    Top-level agent that terminal.py talks to.

    Parameters
    ----------
    agents_cfg_path : str
        Path to agents.yaml. Used to resolve the orchestrator's own cfg
        and to pass agent definitions to ToolHandler for sub-agent spawning.
    plugins_cfg_path : str
        Path to plugins.yaml.
    """

    def __init__(
        self,
        agents_cfg_path: str = "config/agents.yaml",
        plugins_cfg_path: str = "config/plugins.yaml",
    ):
        
        self.agents_cfg = _load_yaml(agents_cfg_path)
        self.plugins_cfg = _load_yaml(plugins_cfg_path)

        # Resolve orchestrator's own LLM config from agents.yaml
        # Expected shape: system_agents.orchestrator: {provider, endpoint, model, ...}
        orchestrator_cfg = dict(self.agents_cfg.get("system_agents", {}).get("planner", {}) or {})
        if not orchestrator_cfg:
            raise ValueError(
                "No 'system_agents.planner' config found in agents.yaml. "
                "Add provider/endpoint/model/timeout_seconds there."
            )
        orchestrator_cfg.setdefault("agent_name", "orchestrator")

        system_prompt = orchestrator_cfg.pop("system_prompt", None)
        log.info(f"Orchestrator system prompt:\n{system_prompt}")

        from langgraph.checkpoint.memory import InMemorySaver
        self.checkpointer = InMemorySaver()

        from langchain_ollama import ChatOllama

        self.llm = ChatOllama(
            model="gpt-oss:120b",
            base_url="http://jcs-macbook-pro:11434",
            temperature=0,
        )

        from langchain.agents import create_agent

        effective_system_prompt = system_prompt or ""
        effective_system_prompt += "\n\nUse at most one tool call per turn."
        effective_system_prompt += "\nWhen calling a tool, return only valid JSON arguments for that tool."
        effective_system_prompt += "\nDo not include reasoning text, markdown, or extra prose inside tool arguments."

        self.agent = create_agent(
            model=self.llm,
            system_prompt=effective_system_prompt,
            tools=SearchTools()._build_executor_tool_list(),
            checkpointer=self.checkpointer,
        )

        self.callbacks = [ToolLogger()]

    def run(self, user_message: str):
        config = {
            "configurable": {"thread_id": "orchestrator-default"},
            "callbacks": self.callbacks,
        }

        payload = {"messages": [{"role": "user", "content": user_message}]}
        try:
            result = self.agent.invoke(payload, config=config)
            return result
        except Exception as exc:
            err = str(exc)
            if "error parsing tool call" not in err:
                raise
            retry_prompt = (
                "Retry the previous request. "
                "If you call a tool, output exactly one tool call and provide only strict JSON arguments with no prose.\n\n"
                f"Original user request: {user_message}"
            )
            retry_payload = {"messages": [{"role": "user", "content": retry_prompt}]}
            result = self.agent.invoke(retry_payload, config=config)
            return result
