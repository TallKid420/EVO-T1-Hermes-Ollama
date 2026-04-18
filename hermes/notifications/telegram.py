import requests, yaml, os

SEVERITY_EMOJI = {
    "Severity.CRITICAL": "🚨",
    "Severity.WARNING": "⚠️",
    "Severity.INFO": "ℹ️",
}

class TelegramNotifier:
    def __init__(self, config: dict = None):
        self.TELEGRAM_TOKEN = config.get("token")
        self.TELEGRAM_CHAT_ID = config.get("chat_id")

    def send(self, message: str, severity: str = "Severity.INFO"):
        if not self.TELEGRAM_TOKEN or not self.TELEGRAM_CHAT_ID:
            print("[NOTIFY] Telegram: missing TOKEN or CHAT_ID")
            return
        emoji = SEVERITY_EMOJI.get(str(severity), "🔔")
        text = f"{emoji} *Hermes*\n{message}"
        try:
            requests.post(
                f"https://api.telegram.org/bot{self.TELEGRAM_TOKEN}/sendMessage",
                json={
                    "chat_id": self.TELEGRAM_CHAT_ID,
                    "text": text,
                    "parse_mode": "Markdown",
                },
                timeout=5,
            )
        except Exception as e:
            print(f"[NOTIFY] Telegram failed: {e}")