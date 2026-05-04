import inspect
import os
import difflib
import importlib

import hermes.executor.tools as tools
from langchain_core.tools import tool, BaseTool


class SearchTools:

    @staticmethod
    def _tool_to_metadata(tool_obj: BaseTool):
        schema = tool_obj.args or {}
        required = []
        if hasattr(tool_obj, "args_schema") and tool_obj.args_schema is not None:
            if hasattr(tool_obj.args_schema, "model_fields"):
                required = [k for k, v in tool_obj.args_schema.model_fields.items() if getattr(v, "is_required", lambda: False)()]
            elif hasattr(tool_obj.args_schema, "__fields__"):
                required = [k for k, v in tool_obj.args_schema.__fields__.items() if getattr(v, "required", False)]
        return {
            "name": tool_obj.name,
            "description": tool_obj.description or "",
            "parameters": {
                "type": "object",
                "properties": schema,
                "required": required,
            },
        }

    @staticmethod
    def _build_executor_tool_list():
        tool_list = []
        base_path = os.path.dirname(tools.__file__)
        folders = os.listdir(base_path)
        for folder in folders:
            folder_path = os.path.join(base_path, folder)

            if not os.path.isdir(folder_path):
                continue

            scripts = []
            for file in os.listdir(folder_path):
                if file.endswith(".py") and file != "__init__.py":
                    scripts.append(os.path.join(folder_path, file))
            for script in scripts:
                module_name = os.path.splitext(os.path.basename(script))[0]

                spec = importlib.util.spec_from_file_location(module_name, script)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                for _, member in inspect.getmembers(module):
                    if not isinstance(member, BaseTool):
                        continue

                    if member.name.startswith("_"):
                        continue

                    tool_list.append(member)

        return tool_list


    @staticmethod
    @tool(
        "search_tool",
        description="Search for tools by natural language query and return best matches.",
        return_direct=False
    )
    def search_tool(query: str):
        tools = SearchTools._build_executor_tool_list()

        names = [t.name for t in tools]

        substring = [t for t in tools if query.lower() in t.name.lower()]

        fuzzy_names = difflib.get_close_matches(query, names, n=5, cutoff=0.0)
        fuzzy = [t for t in tools if t.name in fuzzy_names]

        results = []
        seen = set()

        for t in substring + fuzzy:
            if t.name not in seen:
                results.append(t)
                seen.add(t.name)

        return [SearchTools._tool_to_metadata(t) for t in results[:5]]

