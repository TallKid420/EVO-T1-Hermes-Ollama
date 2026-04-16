"""Demo Ollama executor scaffold."""

from plugins.llm_executor import LLMExecutor


class OllamaExecutorDemo(LLMExecutor):
	"""Demo class for Ollama-backed LLM execution."""

	def __init__(self, model: str | None = None, provider: str | None = "ollama") -> None:
		super().__init__(model=model, provider=provider)

	def configure(self, **kwargs) -> None:
		pass

	def build_messages(self, user_prompt: str, system_prompt: str | None = None) -> list[dict]:
		pass

	def call(self, messages: list[dict], **kwargs) -> dict:
		pass

	def call_with_tools(self, messages: list[dict], tools: list[dict], **kwargs) -> dict:
		pass

	def stream_call(self, messages: list[dict], **kwargs):
		pass

	def parse_response(self, response: dict) -> str:
		pass

	def run(self, user_prompt: str, system_prompt: str | None = None, **kwargs) -> str:
		pass
