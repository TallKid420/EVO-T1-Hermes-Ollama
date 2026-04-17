import json
import os
import time

from ollama import Client

from plugins.llm_executor import LLMExecutor


class OllamaExecutor(LLMExecutor):

    def __init__(self, model: str | None = None, provider: str | None = "ollama") -> None:
        super().__init__(model=model, provider=provider)
        self.host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
        self.model = model or os.getenv("OLLAMA_MODEL", "qwen3")
        self._client: Client | None = None
        self._rpm_interval: float = 3.0
        self._last_call: float = 0.0
        self._request_timeout: float = 30.0
        self._max_retries: int = 2
        self._configured: bool = False

    def _rate_wait(self) -> None:
        now = time.monotonic()
        wait = self._rpm_interval - (now - self._last_call)
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.monotonic()

    def configure(self, **kwargs) -> dict[str, str | float | bool]:
        self.host = kwargs.get("host") or os.getenv("OLLAMA_HOST", self.host)
        self.model = kwargs.get("model") or os.getenv("OLLAMA_MODEL", self.model)
        rpm = float(os.getenv("OLLAMA_RPM_LIMIT", "20"))
        self._debug = os.getenv("OPERATOR_DEBUG", "1").strip().lower() in {"1", "true", "on"}
        self._rpm_interval = 60.0 / max(rpm, 0.01)
        self._client = Client(host=self.host)

        if not self._configured:
            baked_model = f"{self.model}-hermes"
            try:
                self._client.create(model=baked_model, from_=self.model, system=self.get_operator_system_prompt())
                self.model = baked_model
            except Exception:
                pass
            self._configured = True

        self._request_timeout = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "30"))
        self._max_retries = max(0, int(os.getenv("OLLAMA_MAX_RETRIES", "2")))

        return {
            "model": self.model,
            "host": self.host,
            "rpm_interval": self._rpm_interval,
            "debug": self._debug,
            "request_timeout": self._request_timeout,
            "max_retries": self._max_retries,
        }

    def _cache_metrics(self, usage: object) -> tuple[int, int, float, float]:
        if isinstance(usage, dict):
            prompt_tokens = int(usage.get("prompt_eval_count", 0) or 0)
            eval_tokens = int(usage.get("eval_count", 0) or 0)
            total_duration_ns = int(usage.get("total_duration", 0) or 0)
        else:
            prompt_tokens = int(getattr(usage, "prompt_eval_count", 0) or 0)
            eval_tokens = int(getattr(usage, "eval_count", 0) or 0)
            total_duration_ns = int(getattr(usage, "total_duration", 0) or 0)
        total_seconds = total_duration_ns / 1_000_000_000 if total_duration_ns else 0.0
        return prompt_tokens, eval_tokens, total_seconds, 0.0

    def tool_llm(self, messages: list[dict], tools: list[dict] | None = None, **kwargs) -> tuple[str, list[dict], bool]:
        if self._client is None:
            self.configure(**kwargs)
        if tools is None:
            tools = self.tools

        user_messages = [m for m in messages if m.get("role") != "system"]
        self._rate_wait()
        last_exc: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                resp = self._client.chat(
                    model=self.model,
                    messages=user_messages,
                    tools=tools,
                    options={"temperature": 0},
                    think=True,
                    keep_alive=f"{int(max(5, self._request_timeout))}m",
                )
                break
            except Exception as exc:
                last_exc = exc
                if attempt >= self._max_retries:
                    raise
                time.sleep(min(2 ** attempt, 4))
        if last_exc is not None and 'resp' not in locals():
            raise last_exc

        done = bool(getattr(resp, "done", False) or (resp.get("done") if isinstance(resp, dict) else False))
        message = getattr(resp, "message", None) or (resp.get("message", {}) if isinstance(resp, dict) else {})
        content = ((message.get("content", "") if isinstance(message, dict) else getattr(message, "content", "")) or "").strip()

        tool_calls: list[dict] = []
        raw_calls = message.get("tool_calls", []) if isinstance(message, dict) else (getattr(message, "tool_calls", None) or [])
        for idx, tc in enumerate(raw_calls):
            fn = tc.get("function", {}) if isinstance(tc, dict) else getattr(tc, "function", None)
            fn_name = fn.get("name", "") if isinstance(fn, dict) else str(getattr(fn, "name", "") or "")
            fn_args = fn.get("arguments", {}) if isinstance(fn, dict) else (getattr(fn, "arguments", None) or {})
            if isinstance(fn_args, str):
                arg_json = fn_args
            else:
                arg_json = json.dumps(fn_args, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
            tool_calls.append(
                {
                    "id": (tc.get("id", "") if isinstance(tc, dict) else getattr(tc, "id", "")) or f"ollama_call_{idx}",
                    "type": "function",
                    "function": {
                        "name": fn_name,
                        "arguments": arg_json,
                    },
                }
            )

        if self._debug:
            prompt_tokens, eval_tokens, total_seconds, _ = self._cache_metrics(resp)
            print(f"prompt_tokens={prompt_tokens} eval_tokens={eval_tokens} total_s={total_seconds:.2f} done={done}")

        return content, tool_calls, done

    def build_messages(self, user_prompt: str, system_prompt: str | None = None) -> list[dict]:
        messages: list[dict] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})
        return messages

    def call(self, messages: list[dict], **kwargs) -> tuple[str, list[dict], bool]:
        return self.tool_llm(messages, tools=None, **kwargs)

    def call_with_tools(self, messages: list[dict], tools: list[dict], **kwargs) -> tuple[str, list[dict], bool]:
        return self.tool_llm(messages, tools=tools, **kwargs)

    def stream_call(self, messages: list[dict], tools: list[dict] | None = None, **kwargs):
        if self._client is None:
            self.configure(**kwargs)
        if tools is None:
            tools = self.tools
        user_messages = [m for m in messages if m.get("role") != "system"]
        self._rate_wait()
        return self._client.chat(
            model=self.model,
            messages=user_messages,
            tools=tools,
            options={"temperature": 0},
            think=True,
            stream=True,
        )

    def parse_response(self, response: dict) -> str:
        if isinstance(response, tuple) and response:
            return str(response[0])
        return str(response)

    def run(self, user_prompt: str, system_prompt: str | None = None, **kwargs) -> str:
        messages = self.build_messages(user_prompt, system_prompt=system_prompt)
        response = self.call(messages, **kwargs)
        return self.parse_response(response)


class OllamaExecutorDemo(OllamaExecutor):
    pass
