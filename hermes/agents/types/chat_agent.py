from hermes.executor.tools.research import tools
from hermes.agents.base_agent import BaseAgent
from hermes.config_loader import AgentConfig
from typing import Any, Dict
import httpx

TOOLS = [tools.retrieve_relevant_documentation]
class ChatAgent(BaseAgent):
    def __init__(self, config: AgentConfig):
        super().__init__(config)
        self.agent = self._build_runtime()

    def _build_runtime(self):
        from langgraph.checkpoint.memory import InMemorySaver
        from langchain_ollama import ChatOllama
        from langchain.agents import create_agent

        llm = ChatOllama(
            model=self.config.model,
            base_url=self.config.endpoint,
            temperature=self.config.temperature,
        )

        return create_agent(
            model=llm,
            checkpointer=InMemorySaver(),
            tools=TOOLS,
            system_prompt=self.config.system_prompt,
        )

    def run(self, input: str):
        from hermes.executor.toolhandler import ToolLogger

        config: Dict[str, Any] = {
            "configurable": {"thread_id": "chat-default"},
            "callbacks": [ToolLogger()],
        }

        payload = {"messages": [{"role": "user", "content": input}]}

        try:
            return self.agent.invoke(payload, config=config)
        except httpx.ConnectError as exc:
            self.log("Connection Error: Failed to connect to server", "error")
            return {
                "error": True,
                "type": "connection_error",
                "message": str(exc),
            }
        except Exception as exc:
            err = str(exc)
            if "error parsing tool call" not in err:
                self.log(f"Error Caught: \n{err}", "exception")
            self.log("Tool call parse error — retrying with strict prompt", "warning")
            retry_payload = {
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "Retry the previous request. "
                            "If you call a tool, output exactly one tool call "
                            "and provide only strict JSON arguments with no prose.\n\n"
                            f"Original user request: {input}"
                        ),
                    }
                ]
            }
            return self.agent.invoke(retry_payload, config=config)