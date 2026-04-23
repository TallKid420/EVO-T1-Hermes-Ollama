import logging

import requests


log = logging.getLogger(__name__)

SEVERITY_EMOJI = {
    "Severity.CRITICAL": "🚨",
    "Severity.WARNING": "⚠️",
    "Severity.INFO": "ℹ️",
}


class WhatsAppNotifier:
    """Send Hermes system notifications to WhatsApp via CallMeBot."""

    def __init__(self, config: dict = None):
        if not isinstance(config, dict):
            raise ValueError("WhatsAppNotifier config must be a dict")

        self.phone_number = config.get("phone_number")
        self.api_key = config.get("api_key")

        missing = []
        if not self.phone_number:
            missing.append("phone_number")
        if not self.api_key:
            missing.append("api_key")
        if missing:
            raise ValueError(f"Missing required whatsapp config field(s): {missing}")

    def send(self, message: str, severity: str = "Severity.INFO"):
        emoji = SEVERITY_EMOJI.get(str(severity), "🔔")
        text = f"{emoji} Hermes\n{message}"

        try:
            response = requests.get(
                "https://api.callmebot.com/whatsapp.php",
                params={
                    "phone": self.phone_number,
                    "text": text,
                    "apikey": self.api_key,
                },
                timeout=5,
            )
            if response.status_code != 200:
                log.error(
                    "WhatsApp non-200 response: status=%s body=%s",
                    response.status_code,
                    response.text,
                )
        except Exception as e:
            log.exception("WhatsApp send failed: %s", e)