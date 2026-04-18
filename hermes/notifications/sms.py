SEVERITY_EMOJI = {
    "Severity.CRITICAL": "🚨",
    "Severity.WARNING": "⚠️",
    "Severity.INFO": "ℹ️",
}

class SMSNotifier:
    """Stub notifier for SMS; pending concrete implementation."""

    def __init__(self, config: dict = None):
        self.config = config or {}

    def send(self, message: str, severity: str = "Severity.INFO"):
        emoji = SEVERITY_EMOJI.get(str(severity), "🔔")
        text = f"{emoji} *Hermes*\n{message}"
        try:
            raise NotImplementedError("SMSNotifier.send is not implemented yet.")
        except Exception as e:
            print(f"[NOTIFY] SMS failed: {e}")