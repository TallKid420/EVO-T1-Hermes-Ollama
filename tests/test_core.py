import os
import tempfile
import unittest

import executor
import hermes_operator
import settings
from plugins.llm_executor import LLMExecutor, PROVIDER_MODULES


class CoreTests(unittest.TestCase):
    def test_provider_classes_resolve(self):
        ex = LLMExecutor()
        for provider in PROVIDER_MODULES:
            cls = ex._get_provider_class(provider)
            self.assertTrue(callable(cls))

    def test_tool_arg_validation(self):
        ex = LLMExecutor()
        ex.tools = [
            {
                "type": "function",
                "function": {
                    "name": "sample",
                    "parameters": {
                        "type": "object",
                        "required": ["name", "count"],
                        "properties": {
                            "name": {"type": "string"},
                            "count": {"type": "integer"},
                        },
                    },
                },
            }
        ]
        self.assertIsNone(ex._validate_tool_args("sample", {"name": "a", "count": 1}))
        self.assertIn("Missing required argument", ex._validate_tool_args("sample", {"name": "a"}))
        self.assertIn("must be an integer", ex._validate_tool_args("sample", {"name": "a", "count": "1"}))

    def test_run_shell_command(self):
        out = executor.run_shell_command("echo hi", timeout=5)
        self.assertEqual(out.get("returncode"), 0)
        self.assertIn("hi", out.get("stdout", "").lower())

    def test_streaming_plan_path(self):
        old_runtime = hermes_operator._RUNTIME.executor
        old_stream = os.environ.get("OPERATOR_STREAM")
        old_turns = os.environ.get("OPERATOR_MAX_TURNS")

        class FakeExecutor:
            provider = "ollama"
            tools = []

            def get_operator_system_prompt(self):
                return "sys"

            def stream_call(self, messages, **kwargs):
                yield {"message": {"content": "Hello "}, "done": False}
                yield {"message": {"content": "world"}, "done": True}

            def call_with_tools(self, messages):
                return "fallback", [], True

            def normalize_tool_calls(self, calls):
                return calls

            def execute_tool_calls(self, messages, calls):
                return []

            def build_empty_response_message(self):
                return {"role": "system", "content": "continue"}

        try:
            hermes_operator._RUNTIME.executor = FakeExecutor()
            os.environ["OPERATOR_STREAM"] = "1"
            os.environ["OPERATOR_MAX_TURNS"] = "3"
            out = hermes_operator.plan("stream me")
            self.assertTrue(out["done"])
            self.assertEqual(out["assistant_messages"], ["Hello world"])
        finally:
            hermes_operator._RUNTIME.executor = old_runtime
            if old_stream is None:
                os.environ.pop("OPERATOR_STREAM", None)
            else:
                os.environ["OPERATOR_STREAM"] = old_stream
            if old_turns is None:
                os.environ.pop("OPERATOR_MAX_TURNS", None)
            else:
                os.environ["OPERATOR_MAX_TURNS"] = old_turns

    def test_settings_validation(self):
        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as f:
            f.write("LLM_PROVIDER=invalid\n")
            f.write("GROQ_RPM_LIMIT=0\n")
            path = f.name
        try:
            loaded, errors = settings.load_settings_with_validation(path, strict_required=True)
            self.assertEqual(loaded["LLM_PROVIDER"], "groq")
            self.assertTrue(any("LLM Provider" in e for e in errors))
            self.assertTrue(any("RPM Limit" in e for e in errors))
        finally:
            os.remove(path)

    def test_reload_operator_validation_warnings(self):
        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as f:
            f.write("LLM_PROVIDER=groq\n")
            f.write("GROQ_API_KEY=\n")
            f.write("GROQ_RPM_LIMIT=0\n")
            path = f.name

        session_state = {"errors": 0, "status": ""}
        operator_module = type("Op", (), {"setup": staticmethod(lambda env: {"provider": "groq", "model": "m"})})
        try:
            msg = settings.reload_operator(path, operator_module, session_state)
            self.assertIn("Operator reloaded", msg)
            self.assertIn("Validation warnings", msg)
            self.assertIn("validation warning", session_state["status"])
            self.assertEqual(session_state["errors"], 0)
        finally:
            os.remove(path)

    def test_max_turn_bounds(self):
        old_turns = os.environ.get("OPERATOR_MAX_TURNS")
        try:
            os.environ["OPERATOR_MAX_TURNS"] = "-1"
            self.assertEqual(hermes_operator._resolve_max_turns(), 1)
            os.environ["OPERATOR_MAX_TURNS"] = "9999"
            self.assertEqual(hermes_operator._resolve_max_turns(), 200)
            os.environ["OPERATOR_MAX_TURNS"] = "bad"
            self.assertEqual(hermes_operator._resolve_max_turns(), 30)
        finally:
            if old_turns is None:
                os.environ.pop("OPERATOR_MAX_TURNS", None)
            else:
                os.environ["OPERATOR_MAX_TURNS"] = old_turns


if __name__ == "__main__":
    unittest.main()
