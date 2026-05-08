"""
hermes/executor/orchestrator.py

The primary orchestrator agent.
terminal.py calls orchestrator.run(user_message) and prints the result.
"""

from __future__ import annotations

import logging, httpx
from typing import Any, Dict

from hermes.agents.base_agent import BaseAgent
from hermes.executor.toolhandler import ToolLogger
from hermes.executor.search_tools import SearchTools

log = logging.getLogger(__name__)


class Orchestrator:
    """
    Top-level agent that terminal.py talks to.
    Wraps a spawned BaseAgent and exposes a simple run(user_message) interface.
    """

    def __init__(self, agent: BaseAgent):
        self.base_agent = agent
        self.agent = agent.get_runtime()

        self.callbacks = [ToolLogger()]

    def run(self, user_message: str):
        config: Dict[str, Any] = {
            "configurable": {"thread_id": "orchestrator-default"},
            "callbacks": self.callbacks,
        }

        payload = {"messages": [{"role": "user", "content": user_message}]}

        try:
            return self.agent.invoke(payload, config=config)
        except httpx.ConnectError as exc:
            log.error("Connection Error: Failed to connect to server")
            return {
                "error": True,
                "type": "connection_error",
                "message": str(exc),
            }
        except Exception as exc:
            err = str(exc)
            if "error parsing tool call" not in err:
                log.exception(f"Error Caught: \n{err}")
            log.warning("Tool call parse error — retrying with strict prompt")
            retry_payload = {
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "Retry the previous request. "
                            "If you call a tool, output exactly one tool call "
                            "and provide only strict JSON arguments with no prose.\n\n"
                            f"Original user request: {user_message}"
                        ),
                    }
                ]
            }
            return self.agent.invoke(retry_payload, config=config)
