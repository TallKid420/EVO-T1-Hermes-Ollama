from abc import ABC, abstractmethod
from hermes.config_loader import AgentConfig
from hermes.plugins.provider.llm_provider import LLMProvider

class BaseAgent(ABC):
    def __init__(self, config: AgentConfig):
        self.config = config        # stores the YAML config for this agent
        self.langchain_agent = LLMProvider(self.config)     # holds the actual LangSmith agent instance
        self.running = False        # used later for run_loop()

    @abstractmethod
    def run(self, input=None):
        pass                        # every agent MUST implement this

    def run_loop(self):
        pass                        # optional — autonomous agents override this