import logging

import requests


log = logging.getLogger(__name__)

class TelegramCommunicationPlugin:
    def __init__(self, config: dict = None):
        if not isinstance(config, dict):
            raise ValueError("TelegramCommunicationPlugin config must be a dict")
        self.TELEGRAM_TOKEN = config.get("token")
        self.TELEGRAM_CHAT_ID = config.get("chat_id")
        missing = []
        if not self.TELEGRAM_TOKEN:
            missing.append("token")
        if not self.TELEGRAM_CHAT_ID:
            missing.append("chat_id")
        if missing:
            raise ValueError(f"Missing required telegram config field(s): {missing}")

    def send(self, message: str):
        text = f"Hermes: {message}"
        try:
            response = requests.post(
                f"https://api.telegram.org/bot{self.TELEGRAM_TOKEN}/sendMessage",
                json={
                    "chat_id": self.TELEGRAM_CHAT_ID,
                    "text": text,
                    "parse_mode": "Markdown",
                },
                timeout=5,
            )
            if response.status_code != 200:
                log.error(
                    "Telegram non-200 response: status=%s body=%s",
                    response.status_code,
                    response.text,
                )
        except Exception as e:
            log.exception("Telegram send failed: %s", e)

class TelegramNotifier:
    SEVERITY_EMOJI = {
        "Severity.CRITICAL": "🚨",
        "Severity.WARNING": "⚠️",
        "Severity.INFO": "ℹ️",
    }

    def __init__(self, config: dict = None):
        if not isinstance(config, dict):
            raise ValueError("TelegramNotifier config must be a dict")
        self.TELEGRAM_TOKEN = config.get("token")
        self.TELEGRAM_CHAT_ID = config.get("chat_id")
        missing = []
        if not self.TELEGRAM_TOKEN:
            missing.append("token")
        if not self.TELEGRAM_CHAT_ID:
            missing.append("chat_id")
        if missing:
            raise ValueError(f"Missing required telegram config field(s): {missing}")

    def send(self, message: str, severity: str = "Severity.INFO"):
        emoji = self.SEVERITY_EMOJI.get(str(severity), "🔔")
        text = f"{emoji} *Hermes*\n{message}"
        try:
            response = requests.post(
                f"https://api.telegram.org/bot{self.TELEGRAM_TOKEN}/sendMessage",
                json={
                    "chat_id": self.TELEGRAM_CHAT_ID,
                    "text": text,
                    "parse_mode": "Markdown",
                },
                timeout=5,
            )
            if response.status_code != 200:
                log.error(
                    "Telegram non-200 response: status=%s body=%s",
                    response.status_code,
                    response.text,
                )
        except Exception as e:
            log.exception("Telegram send failed: %s", e)