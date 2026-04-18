SEVERITY_EMOJI = {
    "Severity.CRITICAL": "🚨",
    "Severity.WARNING": "⚠️",
    "Severity.INFO": "ℹ️",
}

class SMSNotifier:
    def __init__(self):
        raise NotImplementedError("SMSNotifier is not implemented yet. Please implement the send method.")

    def send(self, message: str, severity: str = "Severity.INFO"):
        emoji = SEVERITY_EMOJI.get(str(severity), "🔔")
        text = f"{emoji} *Hermes*\n{message}"
        try:
            pass #TODO: Implement SMS sending logic here.
        except Exception as e:
            print(f"[NOTIFY] SMS failed: {e}")