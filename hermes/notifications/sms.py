SEVERITY_EMOJI = {
    "Severity.CRITICAL": "🚨",
    "Severity.WARNING": "⚠️",
    "Severity.INFO": "ℹ️",
}

class SMSNotifier:
    """Stub notifier for SMS; pending concrete implementation."""

    def __init__(self, config: dict = None):
        if not isinstance(config, dict) or not config:
            raise ValueError("Missing required sms notifier config")
        self.config = config

    def send(self, message: str, severity: str = "Severity.INFO"):
        raise NotImplementedError("SMSNotifier.send is not implemented yet.")