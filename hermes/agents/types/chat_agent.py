from hermes.agents.base_agent import BaseAgent

class ChatAgent(BaseAgent):
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
            # tools=agent.tools,
            checkpointer=InMemorySaver(),
            system_prompt=self.config.system_prompt,
        )

    def run(self, input=None):
        # actually talk to Ollama and return a response
        return "hello"