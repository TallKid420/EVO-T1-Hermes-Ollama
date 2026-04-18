import logging
from typing import Any, Dict

from hermes.plugins.base import HermesPlugin


logger = logging.getLogger(__name__)


class EchoPlugin(HermesPlugin):
    name = "echo_plugin"
    description = "Lightweight plugin that echoes payload text for integration tests."
    required_permissions = []

    def execute(self, **kwargs: Any) -> Dict[str, Any]:
        message = str(kwargs.get("message", ""))
        logger.info("EchoPlugin executed with message=%s", message)
        return {"ok": True, "plugin": self.name, "echo": message}
