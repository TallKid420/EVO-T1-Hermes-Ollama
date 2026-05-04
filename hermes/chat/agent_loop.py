"""
hermes/executor/agent_loop.py

Generic multi-turn agent loop.
Used by the orchestrator and any sub-agents spawned during execution.
All agents share this loop — only their cfg / system_prompt / tools differ.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List

from hermes.plugins.provider.llm_provider import ChatProvider
from hermes.executor.toolhandler import ToolHandler

log = logging.getLogger(__name__)


@dataclass
class AgentResult:
    content: str
    tool_logs: List[str] = field(default_factory=list)
    completed: bool = False


class AgentLoop:
    """
    Runs a multi-turn LLM loop for a single agent.

    Parameters
    ----------
    cfg : dict
        Agent config (provider, endpoint, model, timeout_seconds, agent_name, …).
    system_prompt : str
        The system prompt for this agent.
    tool_handler : ToolHandler
        Handles execution of tool calls returned by the LLM.
    tools : list[dict] | None
        Tool definitions forwarded to the LLM on every turn.
    max_turns : int
        Hard cap on loop iterations (default: env OPERATOR_MAX_TURNS or 30).
    label : str
        Human-readable name used in log/print output (e.g. "orchestrator", "filesystem_agent").
    """

    def __init__(
        self,
        cfg: Dict[str, Any],
        system_prompt: str,
        tool_handler: ToolHandler,
        tools: list[dict] | None = None,
        max_turns: int | None = None,
        label: str = "agent",
    ):
        self.cfg = cfg
        self.system_prompt = system_prompt
        self.tool_handler = tool_handler
        self.tools = tools or []
        self.max_turns = max_turns if max_turns is not None else self._resolve_max_turns()
        self.label = label
        self._chat = ChatProvider()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, task: str, extra_messages: list[dict] | None = None) -> AgentResult:
        messages = []
        if extra_messages:
            messages.extend(extra_messages)
        messages.append({"role": "user", "content": task})

        tool_logs: list[str] = []
        final_content = ""
        completed = False

        for turn in range(1, self.max_turns + 1):
            try:
                content, tool_calls = self._chat.send_chat_message(
                    prompt=str(messages),
                    cfg=self.cfg,
                    tools=self.tools or None,
                    stream=False,
                )
                done = False if tool_calls != [] else True
            except Exception as exc:
                raise RuntimeError(f"[{self.label}] LLM call failed (turn {turn}): {exc}") from exc

            # Build assistant message entry
            assistant_entry: dict = {"role": "assistant", "content": content}
            if tool_calls != []:
                assistant_entry["tool_calls"] = tool_calls
            messages.append(assistant_entry)

            if tool_calls != []:
                tool_names = ", ".join(tc["function"]["name"] for tc in tool_calls)
                log.info(f"[{self.label}] Step {turn} -> tools: {tool_names}")

                try:
                    tool_result_messages = self.tool_handler.handle(
                        tool_calls=tool_calls,
                        messages=messages,
                        cfg=self.cfg,
                    )
                except Exception as exc:
                    log.error("[%s] ToolHandler failed on turn %d: %s", self.label, turn, exc)
                    # Inject an error result so the LLM can recover
                    tool_result_messages = [
                        {
                            "role": "tool",
                            "tool_call_id": tc.get("id", f"call_{i}"),
                            "content": f"Tool execution error: {exc}",
                        }
                        for i, tc in enumerate(tool_calls)
                    ]

                for msg in tool_result_messages:
                    result_text = msg.get("content", "")
                    tool_logs.append(result_text)
                    # print(f"  [{self.label}] tool result: {result_text[:120]}{'…' if len(result_text) > 120 else ''}")
                    messages.append(msg)

                continue  # next turn — let the LLM process tool results

            if content:
                final_content = content
                if done:
                    completed = True
                    break
                # LLM gave content but done=False — keep looping
                continue

            # Empty content, no tool calls — nudge the model
            log.warning("[%s] Empty response on turn %d, nudging.", self.label, turn)
            messages.append({"role": "user", "content": "Please continue."})

        else:
            print(f"[{self.label}] Reached max turns ({self.max_turns}). Task may be incomplete.")

        return AgentResult(
            content=final_content,
            tool_logs=tool_logs,
            completed=completed,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_max_turns() -> int:
        raw = os.getenv("OPERATOR_MAX_TURNS", "30").strip()
        try:
            value = int(raw)
        except ValueError:
            return 30
        return min(max(value, 1), 200)