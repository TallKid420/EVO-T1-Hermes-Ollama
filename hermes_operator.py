import os
import sys
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

_EXECUTOR: LLMExecutor | None = None


class OperatorSlashCommand(Exception):
    """Raised when slash commands are entered during follow-up prompts."""

    def __init__(self, command: str):
        super().__init__(command)
        self.command = command


def setup(dotenv_path: str = ".env") -> dict[str, object]:
    global _EXECUTOR
    executor = LLMExecutor()
    state = executor.configure(dotenv_path=dotenv_path) or {}
    state.setdefault("provider", executor.provider or "")
    state.setdefault("model", executor.model or "")
    _EXECUTOR = executor
    return state


def _get_executor(dotenv_path: str = ".env") -> LLMExecutor:
    global _EXECUTOR
    if _EXECUTOR is None:
        setup(dotenv_path)
    return _EXECUTOR


def plan(task: str | None = None) -> None:
    try:
        executor = _get_executor()
    except Exception as e:
        raise RuntimeError(f"Operator setup failed: {e}") from e

    if task is None:
        try:
            task = input("Task: ").strip()
        except (EOFError, KeyboardInterrupt):
            return
    if not task:
        return

    print("-" * 60)

    messages: list[dict] = [
        {"role": "system", "content": executor.get_operator_system_prompt()},
        {"role": "user", "content": task},
    ]

    max_turns = int(os.getenv("OPERATOR_MAX_TURNS", "30"))

    for turn in range(1, max_turns + 1):
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
            for line in log_lines:
                print(f"  {line}")

        elif content:
            print(f"\nHermes: {content}")
            if done:
                print("\n[Operator] Task complete.")
                break

        else:
            messages.append(executor.build_empty_response_message())

    else:
        print(f"\n[Operator] Reached max turns ({max_turns}). Task may be incomplete.")