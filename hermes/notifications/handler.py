from hermes.notifications.telegram import TelegramNotifier
from hermes.notifications.gmail import GmailNotifier
from hermes.notifications.sms import SMSNotifier
import yaml

def load_plugins_config(path: str = "config/plugins.yaml") -> dict:
    try:
        with open(path, "r") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        return {}

class NotificationHandler:
    def __init__(self):
        self.config = load_plugins_config()
        active = self.config.get("Active", {})
        self.notifiers = {}
        if active.get("telegram"):
            self.notifiers["telegram"] = TelegramNotifier(
                self.config.get("plugins", {}).get("telegram", {})
            )
        if active.get("gmail"):
            self.notifiers["gmail"] = GmailNotifier(
                self.config.get("plugins", {}).get("gmail", {})
            )
        if active.get("sms"):
            self.notifiers["sms"] = SMSNotifier(
                self.config.get("plugins", {}).get("sms", {})
            )


    def send_notification(self, message: str, severity: str = "Severity.INFO"):
        for notifier in self.notifiers:
            try:
                n = self.notifiers[notifier].send(message, severity)
            except Exception as e:
                print(f"[NotificationHandler] {notifier} failed: {e}")