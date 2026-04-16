import json
import os
import sys
from dataclasses import dataclass
from plugins.llm_executor import LLMExecutor

# Keep the script directory at the end of sys.path so stdlib imports resolve first.
_here = os.path.dirname(os.path.abspath(__file__))
if sys.path and os.path.abspath(sys.path[0]) == _here:
    sys.path.pop(0)
    sys.path.append(_here)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(errors="replace")

@dataclass
class RuntimeState:
    executor: LLMExecutor | None = None


_RUNTIME = RuntimeState()


class OperatorSlashCommand(Exception):
    """Raised when slash commands are entered during follow-up prompts."""

    def __init__(self, command: str):
        super().__init__(command)
        self.command = command


def setup(dotenv_path: str = ".env") -> dict[str, object]:
    executor = LLMExecutor()
    state = executor.configure(dotenv_path=dotenv_path) or {}
    state.setdefault("provider", executor.provider or "")
    state.setdefault("model", executor.model or "")
    _RUNTIME.executor = executor
    return state


def _get_executor(dotenv_path: str = ".env") -> LLMExecutor:
    if _RUNTIME.executor is None:
        setup(dotenv_path)
    return _RUNTIME.executor


def _run_streaming_turn(executor: LLMExecutor, messages: list[dict]) -> tuple[str, list[dict], bool]:
    stream = executor.stream_call(messages, tools=executor.tools)
    content_parts: list[str] = []
    tool_calls: list[dict] = []
    done = False
    printed_prefix = False

    for chunk in stream:
        done = bool(getattr(chunk, "done", False) or (chunk.get("done") if isinstance(chunk, dict) else False))
        message = getattr(chunk, "message", None) or (chunk.get("message", {}) if isinstance(chunk, dict) else {})

        content_piece = message.get("content", "") if isinstance(message, dict) else getattr(message, "content", "")
        if content_piece:
            if not printed_prefix:
                print("\nHermes: ", end="", flush=True)
                printed_prefix = True
            print(content_piece, end="", flush=True)
            content_parts.append(content_piece)

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
                    "id": (tc.get("id", "") if isinstance(tc, dict) else getattr(tc, "id", "")) or f"stream_call_{idx}",
                    "type": "function",
                    "function": {
                        "name": fn_name,
                        "arguments": arg_json,
                    },
                }
            )

    if printed_prefix:
        print()

    return "".join(content_parts).strip(), tool_calls, done


def _resolve_max_turns() -> int:
    raw = os.getenv("OPERATOR_MAX_TURNS", "30").strip()
    try:
        value = int(raw)
    except ValueError:
        return 30
    return min(max(value, 1), 200)


def plan(task: str | None = None) -> dict[str, object]:
    try:
        executor = _get_executor()
    except Exception as e:
        raise RuntimeError(f"Operator setup failed: {e}") from e

    if task is None:
        try:
            task = input("Task: ").strip()
        except (EOFError, KeyboardInterrupt):
            return {"assistant_messages": [], "tool_logs": [], "done": False}
    if not task:
        return {"assistant_messages": [], "tool_logs": [], "done": False}

    print("-" * 60)

    messages: list[dict] = [
        {"role": "system", "content": executor.get_operator_system_prompt()},
        {"role": "user", "content": task},
    ]

    assistant_messages: list[str] = []
    tool_logs: list[str] = []
    completed = False
    stream_requested = os.getenv("OPERATOR_STREAM", "1").strip().lower() in {"1", "true", "on"}
    provider_name = str(getattr(executor, "provider", "") or "").strip().lower()
    stream_enabled = stream_requested and provider_name != "groq"
    max_turns = _resolve_max_turns()

    for turn in range(1, max_turns + 1):
        try:
            if stream_enabled:
                content, calls, done = _run_streaming_turn(executor, messages)
            else:
                content, calls, done = executor.call_with_tools(messages)
        except Exception:
            try:
                content, calls, done = executor.call_with_tools(messages)
            except Exception as e:
                raise RuntimeError(f"LLM call failed (turn {turn}): {e}") from e

        normalized_calls = executor.normalize_tool_calls(calls)

        entry: dict = {"role": "assistant", "content": content}
        if normalized_calls:
            entry["tool_calls"] = normalized_calls
        messages.append(entry)
        calls = normalized_calls

        if calls:
            tool_names = ", ".join(call["function"]["name"] for call in calls)
            print(f"[Step {turn}] -> {tool_names}")

            log_lines = executor.execute_tool_calls(messages, calls)
            tool_logs.extend(log_lines)
            for line in log_lines:
                print(f"  {line}")

        elif content:
            if not stream_enabled:
                print(f"\nHermes: {content}")
            assistant_messages.append(content)
            if done:
                print("\n[Operator] Task complete.")
                completed = True
                break

        else:
            messages.append(executor.build_empty_response_message())

    else:
        print(f"\n[Operator] Reached max turns ({max_turns}). Task may be incomplete.")

    return {
        "assistant_messages": assistant_messages,
        "tool_logs": tool_logs,
        "done": completed,
    }
