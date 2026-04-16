"""
Operator — autonomous multi-step task executor.

Usage:
    python hermes_operator.py                    # interactive
    python hermes_operator.py "build a pong game and run it"
"""

import os
import sys

# Keep the script directory at the end of sys.path so stdlib imports resolve first.
_here = os.path.dirname(os.path.abspath(__file__))
if sys.path and os.path.abspath(sys.path[0]) == _here:
    sys.path.pop(0)
    sys.path.append(_here)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(errors="replace")

import json
import time
from pathlib import Path

from ollama import Client

from executor import EXECUTOR, TOOLS as LOCAL_TOOLS

# Canonicalized tool schema keeps request bytes stable for better cache reuse.
_STATIC_TOOLS = json.loads(json.dumps(LOCAL_TOOLS, sort_keys=True, separators=(",", ":")))

_COMPOUND_MODEL = os.getenv("OPERATOR_COMPOUND_MODEL", "disabled")

STATIC_PROGRESS_CONTINUE = (
    "Continue executing the requested task step by step. "
    "Call tools as needed until all requested outcomes are complete, then announce completion."
)
STATIC_PROGRESS_TOOL_NUDGE = (
    "Proceed with the next concrete step now using a tool call when appropriate."
)

# ── Globals set in main() ─────────────────────────────────────────────────────
_model: str = os.getenv("OLLAMA_MODEL", "qwen3")
_client: Client | None = None
_ollama_host: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")
_rpm_interval: float = 3.0          # seconds between LLM calls
_last_call: float = 0.0
_debug: bool = True


class OperatorSlashCommand(Exception):
    """Raised when slash commands are entered during follow-up prompts."""

    def __init__(self, command: str):
        super().__init__(command)
        self.command = command


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_dotenv(path: str = ".env") -> None:
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def setup(dotenv_path: str = ".env") -> dict[str, str | float]:
    """Load configuration and initialize the Ollama client for operator usage."""
    global _model, _client, _rpm_interval, _COMPOUND_MODEL, _ollama_host

    _load_dotenv(dotenv_path)

    global _debug
    _model = os.getenv("OLLAMA_MODEL", _model)
    _ollama_host = os.getenv("OLLAMA_HOST", _ollama_host)
    _COMPOUND_MODEL = os.getenv("OPERATOR_COMPOUND_MODEL", _COMPOUND_MODEL)
    rpm = float(os.getenv("OLLAMA_RPM_LIMIT", "20"))
    _client = Client(host=_ollama_host)
    _rpm_interval = 60.0 / max(rpm, 0.01)
    _debug = os.getenv("OPERATOR_DEBUG", "1").strip().lower() in {"1", "true", "on"}

    return {
        "model": _model,
        "host": _ollama_host,
        "compound_model": _COMPOUND_MODEL,
        "rpm_interval": _rpm_interval,
        "debug": _debug,
    }


def _rate_wait() -> None:
    global _last_call
    now = time.monotonic()
    wait = _rpm_interval - (now - _last_call)
    if wait > 0:
        time.sleep(wait)
    _last_call = time.monotonic()


def _call_llm_stream(messages: list[dict]) -> tuple[str, list[dict], object]:
    """Stream a completion. Text tokens print live; tool calls accumulate silently.

    Returns (content, tool_call_dicts, usage).
    tool_call_dicts: list of {"id", "type", "function": {"name", "arguments"}} dicts.
    """
    _rate_wait()
    stream = _client.chat(
        model=_model,
        messages=messages,
        tools=_STATIC_TOOLS,
        options={"temperature": 0},
        stream=True,
    )

    content_parts: list[str] = []
    tool_calls: list[dict] = []
    usage: object = None
    printed_prefix = False

    for chunk in stream:
        usage = chunk
        message = chunk.get("message", {}) if isinstance(chunk, dict) else getattr(chunk, "message", None)
        if message is None:
            continue

        # Live-print text tokens
        content_piece = message.get("content", "") if isinstance(message, dict) else getattr(message, "content", "")
        if content_piece:
            if not printed_prefix:
                print("\nHermes: ", end="", flush=True)
                printed_prefix = True
            print(content_piece, end="", flush=True)
            content_parts.append(content_piece)

        # Ollama emits complete tool calls in message.tool_calls.
        chunk_tool_calls = message.get("tool_calls", []) if isinstance(message, dict) else (getattr(message, "tool_calls", None) or [])
        if chunk_tool_calls:
            for idx, tc in enumerate(chunk_tool_calls):
                fn = tc.get("function", {}) if isinstance(tc, dict) else getattr(tc, "function", None)
                if isinstance(fn, dict):
                    fn_name = fn.get("name", "")
                    fn_args = fn.get("arguments", {})
                else:
                    fn_name = str(getattr(fn, "name", "") or "")
                    fn_args = getattr(fn, "arguments", {}) or {}

                if not fn_name:
                    continue

                if isinstance(fn_args, str):
                    fn_args_json = fn_args
                else:
                    fn_args_json = json.dumps(fn_args, ensure_ascii=True, sort_keys=True, separators=(",", ":"))

                tool_calls.append(
                    {
                        "id": f"ollama_call_{len(tool_calls)}",
                        "type": "function",
                        "function": {"name": fn_name, "arguments": fn_args_json},
                    }
                )

    if printed_prefix:
        print()  # newline after streamed text

    content = "".join(content_parts).strip()
    return content, tool_calls, usage


def _cache_metrics(usage: object) -> tuple[int, int, float, float]:
    """Return prompt/eval token counts and wall duration for Ollama responses."""
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


def _execute_tool_calls(messages: list[dict], calls: list) -> list[str]:
    """Run each local tool call, append results to messages, return human-readable log lines.

    calls may be SDK tool-call objects or plain dicts (from streaming).
    """
    log_lines = []
    for c in calls:
        if isinstance(c, dict):
            call_id = c.get("id", "")
            name = (c.get("function") or {}).get("name", "")
            fn_args_raw = (c.get("function") or {}).get("arguments") or {}
        else:
            fn_obj = getattr(c, "function", None)
            call_id = getattr(c, "id", "")
            name = str(getattr(fn_obj, "name", "") or "")
            fn_args_raw = (fn_obj.arguments if fn_obj else None) or {}

        fn = EXECUTOR.get(name)
        if not fn:
            result = {"error": f"Unknown tool: {name}"}
        else:
            try:
                if isinstance(fn_args_raw, str):
                    args = json.loads(fn_args_raw)
                elif isinstance(fn_args_raw, dict):
                    args = fn_args_raw
                else:
                    args = {}
                result = fn(**args)
            except Exception as e:
                result = {"error": str(e)}

        result_json = json.dumps(result, ensure_ascii=True, sort_keys=True, separators=(",", ":"))

        messages.append({
            "role": "tool",
            "tool_call_id": call_id,
            "tool_name": name,
            "content": result_json,
        })

        summary = result_json
        if len(summary) > 180:
            summary = summary[:177] + "..."
        log_lines.append(f"{name} -> {summary}")
    return log_lines


def _is_done(text: str) -> bool:
    t = text.lower()
    return any(phrase in t for phrase in (
        "task complete",
        "task is complete",
        "all done",
        "everything is done",
        "finished the task",
        "completed successfully",
        "i have completed",
        "i've completed",
    ))


def _is_question(text: str) -> bool:
    t = text.strip()
    if t.endswith("?"):
        return True
    lower = t.lower()
    starters = ("would you", "do you want", "should i", "what would", "which",
                "please provide", "can you tell me", "could you", "what is your",
                "what name", "what folder", "where should")
    return any(lower.startswith(s) for s in starters)


# ── Core operator loop ────────────────────────────────────────────────────────

OPERATOR_SYSTEM = (
    "You are an autonomous task-execution agent with access to local tools.\n"
    "When given a task:\n"
    "  1. Briefly outline the steps you will take (1-2 sentences).\n"
    "  2. Execute each step using tools — one tool call at a time.\n"
    "  3. If you need a decision or information from the user, ask a clear question.\n"
    "  4. When all steps are finished, say exactly: TASK COMPLETE — <one-line summary>.\n"
    "Never explain what you just did after a tool call. Never claim you cannot use tools. Always make progress."
)


def plan(task: str | None = None) -> None:
    if _client is None:
        try:
            setup()
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
        {"role": "system", "content": OPERATOR_SYSTEM},
        {"role": "user", "content": task},
    ]

    step_log: list[str] = []   # running log of completed steps
    max_turns = int(os.getenv("OPERATOR_MAX_TURNS", "30"))
    static_progress = os.getenv("OPERATOR_STATIC_PROGRESS", "1").strip().lower() in {"1", "true", "on"}
    last_assistant_text = ""
    same_response_streak = 0
    had_tool_activity = False

    for turn in range(1, max_turns + 1):
        try:
            content, calls, usage = _call_llm_stream(messages)
        except Exception as e:
            raise RuntimeError(f"LLM call failed (turn {turn}): {e}") from e

        if usage is not None and _debug:
            prompt_tokens, eval_tokens, total_seconds, _ = _cache_metrics(usage)
            print(
                f"[Ollama t{turn}] "
                f"prompt_tokens={prompt_tokens} "
                f"eval_tokens={eval_tokens} "
                f"duration={total_seconds:.2f}s"
            )

        # ── Normalize tool call arguments for deterministic replay ────────────
        normalized_calls: list[dict] = []
        for tc in calls:
            raw_args = tc["function"]["arguments"] or "{}"
            try:
                if isinstance(raw_args, str):
                    parsed_args = json.loads(raw_args)
                elif isinstance(raw_args, dict):
                    parsed_args = raw_args
                else:
                    parsed_args = {}
            except Exception as e:
                if _debug:
                    print(f"  [Warn] arg-normalization failed: {e}")
                parsed_args = {}
            normalized_calls.append({
                "id": tc["id"],
                "type": "function",
                "function": {"name": tc["function"]["name"], "arguments": parsed_args},
            })

        # ── Append assistant message ──────────────────────────────────────────
        entry: dict = {"role": "assistant", "content": content}
        if normalized_calls:
            entry["tool_calls"] = normalized_calls
        messages.append(entry)
        calls = normalized_calls  # use normalized dicts for _execute_tool_calls

        # content was already printed live by _call_llm_stream

        # ── Tool calls branch ─────────────────────────────────────────────────
        if calls:
            had_tool_activity = True
            tool_names = ", ".join(c["function"]["name"] for c in calls)
            print(f"[Step {turn}] -> {tool_names}")

            # Preserve any reasoning the model emitted alongside the tool call
            if content:
                step_log.append(f"Step {turn} reasoning: {content[:200]}")

            log_lines = _execute_tool_calls(messages, calls)
            for line in log_lines:
                print(f"  {line}")
                step_log.append(f"Step {turn} ({tool_names}): {line}")

            # Feed progress log back so the model remembers what it already did
            if step_log:
                if static_progress:
                    messages.append({"role": "system", "content": STATIC_PROGRESS_CONTINUE})
                else:
                    messages.append(
                        {
                            "role": "system",
                            "content": (
                                f"Original task: {task!r}\n"
                                f"Completed steps so far:\n" + "\n".join(f"  • {s}" for s in step_log[-12:]) +
                                "\n\nContinue with the next step. Call a tool or announce completion."
                            ),
                        }
                    )

        # ── Text-only branch ───────────────────────────────────────────────────
        elif content:
            if content == last_assistant_text:
                same_response_streak += 1
            else:
                same_response_streak = 0
            last_assistant_text = content

            # Exit if model repeats the same text response twice in a row.
            if same_response_streak >= 1:
                print("\n[Operator] Task complete (duplicate response guard).")
                break

            if _is_done(content):
                print("\n[Operator] Task complete.")
                break

            if _is_question(content):
                # Ask the user and feed the answer back
                try:
                    answer = input("You: ").strip()
                except (EOFError, KeyboardInterrupt):
                    print("\n[Operator] Interrupted.")
                    return

                if answer.startswith("/"):
                    raise OperatorSlashCommand(answer)

                if answer.lower() in {"exit", "quit"}:
                    print("[Operator] Exiting current task.")
                    return

                if not answer:
                    answer = "continue"
                messages.append({"role": "user", "content": answer})
                step_log.append(f"Step {turn}: asked question — user said: {answer[:100]}")
            else:
                # If a tool already ran and the model now gives a direct answer,
                # treat this as completion unless it explicitly asks to continue.
                lower = content.lower()
                continuation_markers = (
                    "next",
                    "then",
                    "after that",
                    "i will",
                    "i'll",
                    "need",
                    "please provide",
                    "which",
                    "where",
                )
                if had_tool_activity and not any(marker in lower for marker in continuation_markers):
                    print("\n[Operator] Task complete (implicit completion).")
                    break

                # Status update / thinking aloud — nudge toward next tool call
                if static_progress:
                    messages.append({"role": "system", "content": STATIC_PROGRESS_TOOL_NUDGE})
                else:
                    messages.append(
                        {
                            "role": "system",
                            "content": (
                                f"Original task: {task!r}\n"
                                f"Completed steps:\n" + "\n".join(f"  • {s}" for s in step_log[-12:]) +
                                "\n\nPlease execute the next step now using a tool call."
                            ),
                        }
                    )

        # ── Empty response ─────────────────────────────────────────────────────
        else:
            messages.append({
                "role": "system",
                "content": "Please continue executing the next step toward completing the task.",
            })

    else:
        print(f"\n[Operator] Reached max turns ({max_turns}). Task may be incomplete.")


# ── Entry point ───────────────────────────────────────────────────────────────

# def main() -> None:
#     try:
#         state = setup()
#     except Exception as e:
#         print(f"Error: {e}", file=sys.stderr)
#         raise SystemExit(1)

#     print(f"Operator ready — model: {state['model']}")
#     print(f"Compound routing model: {state['compound_model']} (via compound_* tools)")
#     print("Type a task and press Enter. /exit to quit.\n")

#     # Allow passing a task directly on the command line
#     # if len(sys.argv) > 1:
#     #     plan(" ".join(sys.argv[1:]))
#     #     return

#     while True:
#         try:
#             user_input = input("Task: ").strip()
#         except (EOFError, KeyboardInterrupt):
#             print()
#             break
#         if not user_input:
#             continue
#         if user_input.lower() in {"/exit", "exit", "quit"}:
#             break
#         plan(user_input)
#         print()


# if __name__ == "__main__":
#     main()