import os
import time

from groq import Groq

from plugins.llm_executor import LLMExecutor

class GroqExecutor(LLMExecutor):

    def __init__(self, model: str | None = None, provider: str | None = "groq") -> None:
        super().__init__(model=model, provider=provider)
        self.model = model or "openai/gpt-oss-20b"
        self._client: Groq | None = None
        self._rpm_interval: float = 3.0
        self._last_call: float = 0.0
        self._debug: bool = True
        self._request_timeout: float = 30.0
        self._max_retries: int = 2
        self.compound_model = os.getenv("OPERATOR_COMPOUND_MODEL", "groq/compound")

    def _rate_wait(self) -> None:
        now = time.monotonic()
        wait = self._rpm_interval - (now - self._last_call)
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.monotonic()

    def configure(self, **kwargs) -> dict[str, str | float | bool]:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError("GROQ_API_KEY not set (.env or env var).")

        self.model = kwargs.get("model") or os.getenv("GROQ_MODEL", self.model or "openai/gpt-oss-120b")
        self.compound_model = os.getenv("OPERATOR_COMPOUND_MODEL", self.compound_model)
        rpm = float(os.getenv("GROQ_RPM_LIMIT", "20"))
        self._client = Groq(api_key=api_key)
        self._rpm_interval = 60.0 / max(rpm, 0.01)
        self._debug = os.getenv("OPERATOR_DEBUG", "1").strip().lower() in {"1", "true", "on"}

        self._request_timeout = float(os.getenv("GROQ_TIMEOUT_SECONDS", "30"))
        self._max_retries = max(0, int(os.getenv("GROQ_MAX_RETRIES", "2")))

        return {
            "model": self.model,
            "compound_model": self.compound_model,
            "rpm_interval": self._rpm_interval,
            "debug": self._debug,
            "request_timeout": self._request_timeout,
            "max_retries": self._max_retries,
        }
    
    def _cache_metrics(self, usage: object) -> tuple[int, int, float, float]:
        """Return prompt_tokens, cached_tokens, cache_hit_pct, estimated_prompt_savings_pct."""
        prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        details = getattr(usage, "prompt_tokens_details", None)
        cached_tokens = int(getattr(details, "cached_tokens", 0) or 0) if details else 0
        cache_hit_pct = (cached_tokens / prompt_tokens * 100.0) if prompt_tokens else 0.0
        # Cached prompt tokens are billed at 50% discount.
        estimated_prompt_savings_pct = (cached_tokens / prompt_tokens * 50.0) if prompt_tokens else 0.0
        return prompt_tokens, cached_tokens, cache_hit_pct, estimated_prompt_savings_pct
    
    def tool_llm(self, messages: list[dict], tools: list[dict] | None = None, **kwargs) -> tuple[str, list[dict], bool]:
        if self._client is None:
            self.configure(**kwargs)
        if tools is None:
            tools = self.tools

        self._rate_wait()
        last_exc: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                resp = self._client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=tools,
                    tool_choice="auto",
                    temperature=0,
                    timeout=self._request_timeout,

                )
                break
            except Exception as exc:
                last_exc = exc
                if attempt >= self._max_retries:
                    raise
                time.sleep(min(2 ** attempt, 4))
        if last_exc is not None and 'resp' not in locals():
            raise last_exc
        done = resp.model_dump().get("choices", [{}])[0].get("finish_reason") == "stop"
        usage = getattr(resp, "usage", None)
        message = resp.choices[0].message if getattr(resp, "choices", None) else None
        content = (getattr(message, "content", "") or "").strip()

        tool_calls: list[dict] = []
        for tc in getattr(message, "tool_calls", None) or []:
            fn = getattr(tc, "function", None)
            tool_calls.append(
                {
                    "id": getattr(tc, "id", "") or "",
                    "type": "function",
                    "function": {
                        "name": str(getattr(fn, "name", "") or ""),
                        "arguments": str(getattr(fn, "arguments", "") or "{}"),
                    },
                }
            )
        if usage is not None and self._debug:
            prompt_tokens, cached_tokens, cache_hit_pct, prompt_savings_pct = self._cache_metrics(usage)
            print(
                f"hit={cache_hit_pct:.1f}% "
                f"cached={cached_tokens}/{prompt_tokens} "
                f"prompt_savings~{prompt_savings_pct:.1f}%"
            )

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

    def stream_call(self, messages: list[dict], **kwargs):
        pass

    def parse_response(self, response: dict) -> str:
        if isinstance(response, tuple) and response:
            return str(response[0])
        return str(response)

    def run(self, user_prompt: str, system_prompt: str | None = None, **kwargs) -> str:
        messages = self.build_messages(user_prompt, system_prompt=system_prompt)
        response = self.call(messages, **kwargs)
        return self.parse_response(response)
