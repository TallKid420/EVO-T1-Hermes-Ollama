import importlib
import inspect
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Type

import yaml

from hermes.core.safety import SafetyManager
from hermes.plugins.base import HermesPlugin


logger = logging.getLogger(__name__)


class PluginManager:
    def __init__(
        self,
        config_path: str = "config/plugins.yaml",
        plugin_dir: Optional[str] = None,
        safety_manager: Optional[SafetyManager] = None,
    ) -> None:
        self.config_path = config_path
        self.plugin_dir = Path(plugin_dir) if plugin_dir else Path(__file__).resolve().parent
        self.safety_manager = safety_manager or SafetyManager()
        self.active_plugins: Dict[str, HermesPlugin] = {}
        self._config: Dict[str, Any] = {}

    def _load_config(self) -> Dict[str, Any]:
        try:
            with open(self.config_path, "r") as f:
                return yaml.safe_load(f) or {}
        except FileNotFoundError:
            logger.warning("Plugin config not found at %s; no plugins will be enabled", self.config_path)
            return {}

    def _discover_module_names(self) -> list[str]:
        names: list[str] = []
        for path in self.plugin_dir.glob("*.py"):
            if path.stem in {"__init__", "base", "loader"}:
                continue
            names.append(path.stem)
        return sorted(names)

    def _resolve_plugin_class(self, module_name: str) -> Optional[Type[HermesPlugin]]:
        module = importlib.import_module(f"hermes.plugins.{module_name}")
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if (
                issubclass(obj, HermesPlugin)
                and obj is not HermesPlugin
                and obj.__module__ == module.__name__
            ):
                return obj
        return None

    def _is_enabled(self, plugin_name: str, plugin_cfg: Dict[str, Any]) -> bool:
        if "enabled" in plugin_cfg:
            return bool(plugin_cfg.get("enabled"))

        active_cfg = self._config.get("active") or self._config.get("Active") or {}
        if isinstance(active_cfg, dict) and plugin_name in active_cfg:
            return bool(active_cfg[plugin_name])

        return False

    def _plugin_config(self, plugin_name: str) -> Dict[str, Any]:
        plugins_cfg = self._config.get("plugins", {})
        raw_cfg = plugins_cfg.get(plugin_name, {}) if isinstance(plugins_cfg, dict) else {}
        if not isinstance(raw_cfg, dict):
            return {}
        return {k: v for k, v in raw_cfg.items() if k != "enabled"}

    def _raw_plugin_config(self, plugin_name: str) -> Dict[str, Any]:
        plugins_cfg = self._config.get("plugins", {})
        raw_cfg = plugins_cfg.get(plugin_name, {}) if isinstance(plugins_cfg, dict) else {}
        if not isinstance(raw_cfg, dict):
            return {}
        return raw_cfg

    def load_plugins(self) -> Dict[str, HermesPlugin]:
        self._config = self._load_config()
        self.active_plugins = {}

        for module_name in self._discover_module_names():
            try:
                plugin_cls = self._resolve_plugin_class(module_name)
                if plugin_cls is None:
                    logger.debug("No HermesPlugin implementation found in module %s", module_name)
                    continue

                plugin = plugin_cls()
                plugin_name = plugin.name or module_name
                raw_plugin_cfg = self._raw_plugin_config(plugin_name)
                plugin_cfg = self._plugin_config(plugin_name)

                if not self._is_enabled(plugin_name, raw_plugin_cfg):
                    logger.info("Plugin %s is disabled; skipping", plugin_name)
                    continue

                required_permissions = plugin.required_permissions or []
                self.safety_manager.register_plugin_permissions(plugin_name, required_permissions)
                self.safety_manager.check_plugin_permissions(required_permissions)

                plugin.initialize(plugin_cfg)
                self.active_plugins[plugin_name] = plugin
                logger.info("Loaded plugin %s", plugin_name)
            except Exception:
                logger.exception("Failed loading plugin module %s", module_name)

        return self.active_plugins

    def execute_plugin(self, plugin_name: str, **kwargs: Any) -> Any:
        plugin = self.active_plugins.get(plugin_name)
        if plugin is None:
            raise KeyError(f"Plugin not loaded: {plugin_name}")
        return plugin.execute(**kwargs)

    def shutdown_all(self) -> None:
        for plugin_name, plugin in self.active_plugins.items():
            try:
                plugin.shutdown()
            except Exception:
                logger.exception("Failed to shutdown plugin %s", plugin_name)
