from __future__ import annotations
from dataclasses import dataclass
from collections import deque
from typing import Deque, Dict
from trader_tool.domain.models import Features, Signal, Side

@dataclass
class MomentumConfig:
    fast: int = 10
    slow: int = 30
    min_atr: float = 1.0
    min_conf: float = 0.55

class MomentumStrategy:
    name = "Momentum (SMA Cross)"

    def __init__(self, cfg: MomentumConfig | None = None):
        self.cfg = cfg or MomentumConfig()
        self._prices: Dict[str, Deque[float]] = {}

    def _dq(self, symbol: str) -> Deque[float]:
        if symbol not in self._prices:
            self._prices[symbol] = deque(maxlen=max(self.cfg.slow, 60))
        return self._prices[symbol]

    @staticmethod
    def _sma(vals: list[float]) -> float:
        return sum(vals) / len(vals) if vals else 0.0

    def on_features(self, f: Features) -> Signal | None:
        if f.news_risk >= 0.75:
            return Signal(ts=f.ts, symbol=f.symbol, side=Side.WAIT, confidence=0.9,
                          rationale="Notícia alto impacto: WAIT (reduzir risco).",
                          meta={"news_risk": f.news_risk})

        dq = self._dq(f.symbol)
        dq.append(float(f.price))

        if len(dq) < self.cfg.slow:
            return Signal(ts=f.ts, symbol=f.symbol, side=Side.WAIT, confidence=0.65,
                          rationale=f"Aquecendo dados: {len(dq)}/{self.cfg.slow} preços.",
                          meta={"warmup": True, "count": len(dq)})

        if f.atr < self.cfg.min_atr:
            return Signal(ts=f.ts, symbol=f.symbol, side=Side.WAIT, confidence=0.6,
                          rationale=f"ATR baixo ({f.atr:.2f}) < {self.cfg.min_atr:.2f}: WAIT.",
                          meta={"atr": f.atr})

        vals = list(dq)
        fast = self._sma(vals[-self.cfg.fast:])
        slow = self._sma(vals[-self.cfg.slow:])
        diff = fast - slow

        conf = min(0.95, max(self.cfg.min_conf, 0.55 + abs(diff) / max(1.0, f.atr * 3)))
        if f.book_imbalance:
            conf = min(0.95, conf + min(0.08, abs(f.book_imbalance) * 0.08))

        if diff > 0:
            return Signal(ts=f.ts, symbol=f.symbol, side=Side.BUY, confidence=conf,
                          rationale=f"SMA altista: SMA{self.cfg.fast}={fast:.2f} > SMA{self.cfg.slow}={slow:.2f}",
                          meta={"fast": fast, "slow": slow, "diff": diff, "atr": f.atr})
        return Signal(ts=f.ts, symbol=f.symbol, side=Side.SELL, confidence=conf,
                      rationale=f"SMA baixista: SMA{self.cfg.fast}={fast:.2f} < SMA{self.cfg.slow}={slow:.2f}",
                      meta={"fast": fast, "slow": slow, "diff": diff, "atr": f.atr})
