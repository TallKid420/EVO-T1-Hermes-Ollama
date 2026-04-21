SEVERITY_EMOJI = {
    "Severity.CRITICAL": "🚨",
    "Severity.WARNING": "⚠️",
    "Severity.INFO": "ℹ️",
}

class GmailNotifier:
    """Stub notifier for Gmail; pending concrete implementation."""

    def __init__(self, config: dict = None):
        if not isinstance(config, dict) or not config:
            raise ValueError("Missing required gmail notifier config")
        self.config = config

    def send(self, message: str, severity: str = "Severity.INFO"):
        raise NotImplementedError("GmailNotifier.send is not implemented yet.")