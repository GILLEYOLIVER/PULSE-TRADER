from __future__ import annotations
from trading_assistant.config import ExecutionConfig

class OrderRouter:
    """Legacy execution retired. All new entries must use the persistent v2 risk path."""
    def __init__(self,config:ExecutionConfig):
        self.config=config
        if config.mode.lower()!="paper":raise PermissionError("LIVE execution is disabled")
    async def execute(self,order,state):
        raise PermissionError("Use PULSE-TRADER 2.0 PaperEngine: legacy execution lacks a persistent risk ledger")
