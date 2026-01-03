from __future__ import annotations

from dataclasses import asdict

from trading_assistant.config import NotifierConfig
from trading_assistant.core.models import ExecutionReport


class Notifier:
    def __init__(self, config: NotifierConfig) -> None:
        self.config = config

    def notify_execution(self, report: ExecutionReport) -> None:
        if not self.config.enabled:
            return
        if self.config.console:
            print("[EXEC]", asdict(report))
