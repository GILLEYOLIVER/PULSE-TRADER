from __future__ import annotations
from dataclasses import dataclass
from trader_tool.domain.models import Features, Signal, Side

@dataclass
class BreakoutConfig:
    min_atr: float = 2.0
    min_conf: float = 0.55

class BreakoutStrategy:
    name = "Breakout"

    def __init__(self, cfg: BreakoutConfig | None = None):
        self.cfg = cfg or BreakoutConfig()
        self._last_side: Side = Side.WAIT

    def on_features(self, f: Features) -> Signal | None:
        # filtro de risco por notícia: se alto, só WAIT
        if f.news_risk >= 0.7:
            return Signal(ts=f.ts, symbol=f.symbol, side=Side.WAIT, confidence=0.9,
                          rationale="Notícia de alto impacto: reduzir risco (WAIT).",
                          meta={"news_risk": f.news_risk})

        # precisa de ATR mínimo
        if f.atr < self.cfg.min_atr:
            return None

        # breakout simples usando retorno + book
        score = (f.ret_1 * 5.0) + (f.book_imbalance * 0.5)
        if score > 0.6:
            conf = min(0.95, 0.55 + score/2)
            if conf < self.cfg.min_conf:
                return None
            return Signal(ts=f.ts, symbol=f.symbol, side=Side.BUY, confidence=conf,
                          rationale=f"Breakout: ret_1={f.ret_1:.4f}, imb={f.book_imbalance:.2f}",
                          meta={"score": score, "atr": f.atr})
        if score < -0.6:
            conf = min(0.95, 0.55 + abs(score)/2)
            if conf < self.cfg.min_conf:
                return None
            return Signal(ts=f.ts, symbol=f.symbol, side=Side.SELL, confidence=conf,
                          rationale=f"Breakdown: ret_1={f.ret_1:.4f}, imb={f.book_imbalance:.2f}",
                          meta={"score": score, "atr": f.atr})

        return None
