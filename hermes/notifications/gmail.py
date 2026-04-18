SEVERITY_EMOJI = {
    "Severity.CRITICAL": "🚨",
    "Severity.WARNING": "⚠️",
    "Severity.INFO": "ℹ️",
}

class GmailNotifier:
    def __init__(self):
        raise NotImplementedError("GmailNotifier is not implemented yet. Please implement the send method.")

    def send(self, message: str, severity: str = "Severity.INFO"):
        emoji = SEVERITY_EMOJI.get(str(severity), "🔔")
        text = f"{emoji} *Hermes*\n{message}"
        try:
            pass #TODO: Implement Gmail sending logic here.
        except Exception as e:
            print(f"[NOTIFY] SMS failed: {e}")