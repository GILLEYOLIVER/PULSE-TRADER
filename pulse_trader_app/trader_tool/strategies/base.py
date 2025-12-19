from __future__ import annotations
from abc import ABC, abstractmethod
from trader_tool.domain.models import Features, Signal

class Strategy(ABC):
    name: str = "Strategy"

    @abstractmethod
    def on_features(self, f: Features) -> Signal | None:
        raise NotImplementedError
