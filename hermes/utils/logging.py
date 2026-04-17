import json
from datetime import datetime


class Logger:
    def __init__(self, log_file="hermes.log"):
        self.log_file = log_file

    def _write(self, data: dict):
        with open(self.log_file, "a") as f:
            f.write(json.dumps(data) + "\n")

    def action(self, action, service=None, result=None, success=True, metadata=None):
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "type": "action",
            "action": action,
            "service": service,
            "result": result,
            "success": success,
            "metadata": metadata or {},
        }
        self._write(log_entry)

    def event(self, message, severity):
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "type": "event",
            "message": message,
            "severity": severity,
        }
        self._write(log_entry)