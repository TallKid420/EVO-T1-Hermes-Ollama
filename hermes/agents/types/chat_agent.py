from hermes.agents.base_agent import BaseAgent

class ChatAgent(BaseAgent):
    def run(self, input=None):
        # actually talk to Ollama and return a response
        return "hello"