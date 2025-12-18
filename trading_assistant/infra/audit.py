from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from typing import Any, Dict

from trading_assistant.config import AuditConfig


class AuditLogger:
    def __init__(self, config: AuditConfig) -> None:
        self.config = config

    def info(self, event: str, payload: Dict[str, Any]) -> None:
        if not self.config.enabled:
            return
        rec = {"ts": datetime.utcnow().isoformat(), "event": event, "payload": payload}
        try:
            with open(self.config.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except Exception:
            pass
