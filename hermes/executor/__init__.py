import importlib
import pkgutil

from langchain_core.tools import BaseTool


def _discover_executor_commands():
    executor_commands = {}
    try:
        import hermes.executor.tools as executor_tools_pkg

        for _, module_name, is_pkg in pkgutil.walk_packages(executor_tools_pkg.__path__, executor_tools_pkg.__name__ + "."):
            if is_pkg:
                continue
            try:
                module = importlib.import_module(module_name)
            except Exception:
                continue
            for attr_name in dir(module):
                if attr_name.startswith("_"):
                    continue
                attr = getattr(module, attr_name)
                if isinstance(attr, BaseTool):
                    executor_commands[attr.name] = attr
    except Exception:
        pass
    return executor_commands


EXECUTOR = _discover_executor_commands()
