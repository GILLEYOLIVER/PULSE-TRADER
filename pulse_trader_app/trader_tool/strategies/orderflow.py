from __future__ import annotations
from dataclasses import dataclass
from trader_tool.domain.models import Features, Signal, Side

@dataclass
class OrderflowConfig:
    min_imbalance: float = 0.35
    min_conf: float = 0.6

class OrderflowStrategy:
    name = "Orderflow"

    def __init__(self, cfg: OrderflowConfig | None = None):
        self.cfg = cfg or OrderflowConfig()

    def on_features(self, f: Features) -> Signal | None:
        if f.news_risk >= 0.8:
            return Signal(ts=f.ts, symbol=f.symbol, side=Side.WAIT, confidence=0.9,
                          rationale="Alto risco de notícia: WAIT (proteção).",
                          meta={"news_risk": f.news_risk})

        imb = f.book_imbalance
        if abs(imb) < self.cfg.min_imbalance:
            return None

        side = Side.BUY if imb > 0 else Side.SELL
        conf = min(0.95, self.cfg.min_conf + (abs(imb) - self.cfg.min_imbalance))
        rationale = f"Orderflow: book_imbalance={imb:.2f} (side={side})"
        return Signal(ts=f.ts, symbol=f.symbol, side=side, confidence=conf, rationale=rationale,
                      meta={"imb": imb})
