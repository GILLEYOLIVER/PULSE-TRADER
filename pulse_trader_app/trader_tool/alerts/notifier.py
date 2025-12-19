from __future__ import annotations
from dataclasses import dataclass
import logging

logger = logging.getLogger("pulse.alerts")

@dataclass
class Alert:
    title: str
    message: str
    level: str = "INFO"  # INFO/WARN/ERROR

class Notifier:
    def send(self, alert: Alert):
        raise NotImplementedError

class LogNotifier(Notifier):
    def send(self, alert: Alert):
        if alert.level == "ERROR":
            logger.error("%s | %s", alert.title, alert.message)
        elif alert.level == "WARN":
            logger.warning("%s | %s", alert.title, alert.message)
        else:
            logger.info("%s | %s", alert.title, alert.message)
