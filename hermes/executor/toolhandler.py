from hermes.executor.search_tools import SearchTools
import hermes.executor as executor_package
from langchain_core.tools import BaseTool
from langchain_core.callbacks import BaseCallbackHandler
import inspect, json, logging

log = logging.getLogger(__name__)

class ToolLogger(BaseCallbackHandler):
    def on_tool_start(self, serialized, input_str, **kwargs):
        log.info(f"\n[TOOL CALL]\nname: {serialized.get('name')}\nargs: {input_str}")

    def on_tool_end(self, output, **kwargs):
        log.info(f"\n[TOOL RESULT]\n{output}")

class ToolHandler:

    @staticmethod
    def get_search_tools(**kwargs):
        tools = []

        for _, member in inspect.getmembers(SearchTools):
            if not isinstance(member, BaseTool):
                continue

            # Tool name defined by @tool
            name = member.name

            # If explicitly disabled → skip
            if name in kwargs and kwargs[name] is False:
                continue

            tools.append(member)

        return tools

    # -----------------------------
    # TOOL EXECUTION
    # -----------------------------
    @staticmethod
    def handle(tool_calls, messages, cfg):
        if not tool_calls:
            raise ValueError("No tool calls provided")

        call = tool_calls[0]
        fn_data = call.get("function", {})

        name = fn_data.get("name")
        arguments = fn_data.get("arguments", {})

        # -----------------------------
        # FUNCTION RESOLUTION
        # -----------------------------
        if name == "search_tool":
            func = getattr(SearchTools, name, None)
        else:
            func = executor_package.EXECUTOR.get(name)

        if isinstance(func, BaseTool):
            is_executable = True
        else:
            is_executable = callable(func)

        if not is_executable:
            available = sorted(getattr(executor_package, "EXECUTOR", {}).keys())
            raise ValueError(f"Tool '{name}' not found or not callable. Available tools: {available}")

        # -----------------------------
        # ARG NORMALIZATION FIX
        # -----------------------------
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except Exception:
                arguments = {"query": arguments}

        print(f"[Tool Args]: {arguments}")

        # -----------------------------
        # EXECUTE
        # -----------------------------
        try:
            if isinstance(func, BaseTool):
                if isinstance(arguments, dict):
                    result = func.invoke(arguments)
                else:
                    result = func.invoke({"query": arguments})
            elif isinstance(arguments, dict):
                result = func(**arguments)
            else:
                result = func(arguments)
        except Exception as e:
            raise RuntimeError(f"Tool execution failed: {e}")

        print(f"[Tool Result]: {result}")

        # -----------------------------
        # RESPONSE FORMATTING
        # -----------------------------
        if isinstance(result, list) and all(isinstance(i, dict) for i in result):
            return result

        content = result if isinstance(result, str) else json.dumps(result, indent=2)

        return [
            {
                "role": "tool",
                "tool_call_id": call.get("id", "tool"),
                "content": content,
            }
        ]