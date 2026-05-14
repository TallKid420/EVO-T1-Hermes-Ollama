from hermes.plugins.communication.telegram import TelegramNotifier
from hermes.plugins.communication.gmail import GmailNotifier
from hermes.plugins.communication.sms import SMSNotifier
from hermes.plugins.communication.whatsapp import WhatsAppNotifier
import yaml
import logging


log = logging.getLogger(__name__)

Notifiers_mapping = {
    "telegram": TelegramNotifier,
    "gmail": GmailNotifier,
    "sms": SMSNotifier,
    "whatsapp": WhatsAppNotifier,
}

def load_plugins_config(path: str = "config/plugins.yaml") -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f) or {}

class NotificationHandler:
    def __init__(self):
        self.notifiers = {}
        try:
            self.config = load_plugins_config()
        except Exception as e:
            self.config = {}
            log.warning("Failed to load plugins config: %s", e)
            return

        active = self.config.get("active", {}).get("communication")
        if not isinstance(active, dict):
            log.warning("Missing or invalid notification config key: active.communication")
            return

        for name, settings in active.items():
            if not isinstance(settings, dict):
                continue
            if not settings.get("system_notifications"):
                continue
            notifier_cls = Notifiers_mapping.get(name)
            if not notifier_cls:
                continue
            try:
                self.notifiers[name] = notifier_cls(self.config.get("plugins", {}).get(name, {}))
            except Exception as e:
                log.warning("Notifier '%s' initialization failed: %s", name, e)


    def send_notification(self, message: str, severity: str = "Severity.INFO"):
        if not self.notifiers:
            log.debug("No active notifiers configured")
            return

        for name, notifier in self.notifiers.items():
            try:
                notifier.send(message, severity)
                log.info("Notifier '%s' sent message", name)
            except NotImplementedError as e:
                log.warning("Notifier '%s' not implemented: %s", name, e)
            except Exception as e:
                log.exception("Notifier '%s' failed: %s", name, e)
