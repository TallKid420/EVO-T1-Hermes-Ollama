import importlib
import json
import os
from pathlib import Path
from executor import EXECUTOR, TOOLS as LOCAL_TOOLS


PROVIDER_MODULES = {
    "ollama": ("plugins.ollama", "OllamaExecutorDemo"),
    "groq": ("plugins.groq", "GroqExecutorDemo"),
}

class LLMExecutor:
    OPERATOR_SYSTEM = (
        "You are an autonomous task-execution agent with access to local tools.\n"
        "When given a task:\n"
        "  1. Briefly outline the steps you will take (1-2 sentences).\n"
        "  2. Execute each step using tools — one tool call at a time.\n"
        "  3. If you need a decision or information from the user, use the ask_question tool. Do not ask the user directly in assistant text.\n"
        "Never explain what you just did after a tool call. Never claim you cannot use tools. Always make progress."
    )

    def __init__(self, model: str | None = None, provider: str | None = None) -> None:
        self.model = model
        self.provider = provider
        self.tools = json.loads(json.dumps(LOCAL_TOOLS, sort_keys=True, separators=(",", ":")))
        self.backend = None

    def _get_provider_class(self, provider: str):
        module_name, class_name = PROVIDER_MODULES[provider]
        module = importlib.import_module(module_name)
        return getattr(module, class_name)

    def _load_dotenv(self, path: str = ".env") -> None:
        p = Path(path)
        if not p.exists():
            return
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

    def configure(self, **kwargs):
        dotenv_path = kwargs.pop("dotenv_path", ".env")
        self._load_dotenv(dotenv_path)

        provider = kwargs.pop("provider", None) or self.provider or os.getenv("LLM_PROVIDER", "groq")
        provider = provider.strip().lower()
        if provider not in PROVIDER_MODULES:
            raise ValueError(f"Unsupported LLM provider: {provider}")

        self.provider = provider
        executor_class = self._get_provider_class(provider)

        if self.backend is None or self.backend.provider != provider:
            self.backend = executor_class(model=self.model, provider=provider)

        state = self.backend.configure(**kwargs)
        self.model = getattr(self.backend, "model", self.model)
        return state

    def _operator_owner(self):
        return self.backend or self

    def get_debug_enabled(self) -> bool:
        return bool(getattr(self._operator_owner(), "_debug", False))

    def get_operator_system_prompt(self) -> str:
        return str(getattr(self._operator_owner(), "OPERATOR_SYSTEM", self.OPERATOR_SYSTEM))

    def normalize_tool_calls(self, calls: list) -> list[dict]:
        normalized_calls: list[dict] = []
        for tc in calls:
            if isinstance(tc, dict):
                call_id = tc.get("id", "")
                fn_data = tc.get("function") or {}
                name = str(fn_data.get("name", "") or "")
                raw_args = fn_data.get("arguments") or "{}"
            else:
                fn_obj = getattr(tc, "function", None)
                call_id = getattr(tc, "id", "")
                name = str(getattr(fn_obj, "name", "") or "")
                raw_args = (getattr(fn_obj, "arguments", None) if fn_obj else None) or "{}"

            try:
                parsed_args = json.loads(raw_args)
                norm_args = json.dumps(parsed_args, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
            except Exception as exc:
                if self.get_debug_enabled():
                    print(f"  [Warn] arg-normalization failed: {exc}")
                norm_args = raw_args

            normalized_calls.append(
                {
                    "id": call_id,
                    "type": "function",
                    "function": {"name": name, "arguments": norm_args},
                }
            )
        return normalized_calls

    def execute_tool_calls(self, messages: list[dict], calls: list[dict]) -> list[str]:
        log_lines: list[str] = []
        for call in calls:
            call_id = call.get("id", "")
            fn_data = call.get("function") or {}
            name = fn_data.get("name", "")
            fn_args_str = fn_data.get("arguments") or "{}"

            fn = EXECUTOR.get(name)
            if not fn:
                result = {"error": f"Unknown tool: {name}"}
            else:
                try:
                    args = json.loads(fn_args_str)
                    result = fn(**args)
                except Exception as exc:
                    result = {"error": str(exc)}

            result_json = json.dumps(result, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call_id,
                    "name": name,
                    "content": result_json,
                }
            )

            summary = result_json if len(result_json) <= 180 else result_json[:177] + "..."
            log_lines.append(f"{name} -> {summary}")
        return log_lines

    def build_empty_response_message(self) -> dict[str, str]:
        return {
            "role": "system",
            "content": "Please continue executing the next step toward completing the task.",
        }

    def build_messages(self, user_prompt: str, system_prompt: str | None = None) -> list[dict]:
        pass

    def call(self, messages: list[dict], **kwargs) -> dict:
        if self.backend is None:
            self.configure()
        return self.backend.call(messages, **kwargs)

    def call_with_tools(self, messages: list[dict], tools: list[dict] | None = None, **kwargs) -> dict:
        if tools is None:
            tools = self.tools
        if messages is None:
            raise ValueError("Messages must be provided for LLM calls.")
        if self.backend is None:
            self.configure()
        return self.backend.tool_llm(messages, tools, **kwargs)

    def stream_call(self, messages: list[dict], **kwargs):
        if self.backend is None:
            self.configure()
        return self.backend.stream_call(messages, **kwargs)

    def parse_response(self, response: dict) -> str:
        if self.backend is None:
            self.configure()
        return self.backend.parse_response(response)

    def run(self, user_prompt: str, system_prompt: str | None = None, **kwargs) -> str:
        if self.backend is None:
            self.configure()
        return self.backend.run(user_prompt, system_prompt=system_prompt, **kwargs)
