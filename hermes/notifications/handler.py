from hermes.notifications.telegram import TelegramNotifier
from hermes.notifications.gmail import GmailNotifier
from hermes.notifications.sms import SMSNotifier
import yaml
import logging


log = logging.getLogger(__name__)

def load_plugins_config(path: str = "config/plugins.yaml") -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f) or {}

class NotificationHandler:
    def __init__(self):
        self.config = load_plugins_config()
        active = self.config.get("active") or self.config.get("Active", {})
        if not isinstance(active, dict):
            raise ValueError("Missing or invalid notification config key: active")
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
        if not self.notifiers:
            log.warning("No active notifiers configured")
            return

        for name, notifier in self.notifiers.items():
            try:
                notifier.send(message, severity)
                log.info("Notifier '%s' sent message", name)
            except NotImplementedError as e:
                log.warning("Notifier '%s' not implemented: %s", name, e)
            except Exception as e:
                log.exception("Notifier '%s' failed: %s", name, e)