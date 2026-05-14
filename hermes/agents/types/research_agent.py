from hermes.executor.tools.research import tools
from hermes.agents.base_agent import BaseAgent
from hermes.config_loader import AgentConfig
from typing import Any, Dict
import httpx

RESEARCH_TOOLS = [tools.crawl_data, tools.retrieve_relevant_documentation]

RESEARCH_SYSTEM_PROMPT = """
You are Hermes Research Agent.
Rules:
- Always use tools before answering factual questions.
- Provide citations for factual claims.
- If confidence is low, say what is unknown.
- If information on the topic does not exist in the database use crawl_data to add more info into the database then check again
""".strip()

class ResearcherAgent(BaseAgent):

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
            tools=RESEARCH_TOOLS,
            checkpointer=InMemorySaver(),
            system_prompt=self.config.system_prompt or RESEARCH_SYSTEM_PROMPT,
        )

    def run(self, input: str):
        from hermes.executor.toolhandler import ToolLogger

        config: Dict[str, Any] = {
            "configurable": {"thread_id": f"research-{self.agent_id}"},
            "callbacks": [ToolLogger()],
        }

        payload = {"messages": [{"role": "user", "content": input}]}

        try:
            return self.agent.invoke(payload, config=config)
        except httpx.ConnectError as exc:
            return {"error": True, "type": "connection_error", "message": str(exc)}