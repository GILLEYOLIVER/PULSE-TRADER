from __future__ import annotations

from datetime import datetime
from typing import Optional

from trading_assistant.config import SignalEngineConfig
from trading_assistant.core.models import Signal
from trading_assistant.core.state import MarketState
from trading_assistant.signals.technicals import atr, ema


class SignalEngine:
    """Motor simples e explicável (sem ML) para BUY/SELL/WAIT.

    Score = tendência (EMA) + momentum (distância) + (confirmação/penalidade por notícias).
    """

    def __init__(self, config: SignalEngineConfig) -> None:
        self.config = config

    def generate_signal(self, state: MarketState, symbol: Optional[str] = None) -> Optional[Signal]:
        symbol = symbol or (next(iter(state.last_price.keys()), None))
        if not symbol:
            return None

        candles = state.get_last_candles(symbol, n=200)
        if len(candles) < max(self.config.ema_slow, self.config.atr_period) + 5:
            return None

        closes = [c.close for c in candles]
        highs = [c.high for c in candles]
        lows = [c.low for c in candles]

        e_fast = ema(closes[-(self.config.ema_slow * 2):], self.config.ema_fast)
        e_slow = ema(closes[-(self.config.ema_slow * 2):], self.config.ema_slow)
        a = atr(highs[-(self.config.atr_period * 3):], lows[-(self.config.atr_period * 3):], closes[-(self.config.atr_period * 3):], self.config.atr_period)

        if e_fast is None or e_slow is None or a is None or a <= 0:
            return None

        price = float(closes[-1])
        trend = 1.0 if e_fast > e_slow else -1.0 if e_fast < e_slow else 0.0
        momentum = (price - e_slow) / max(a, 1e-9)  # em unidades de ATR

        news_impact = float(state.news_impact.get(symbol, 0.0))

        # Penaliza operar em notícias MUITO fortes (puxa para WAIT)
        news_penalty = min(2.0, max(0.0, news_impact / 2.5))

        score = trend + momentum - news_penalty

        side = "WAIT"
        if score >= self.config.threshold:
            side = "BUY"
        elif score <= -self.config.threshold:
            side = "SELL"

        # Stops/alvos baseados em ATR (simples e eficaz)
        sl_dist = 1.2 * a
        tp_dist = 1.8 * a

        if side == "BUY":
            sl = price - sl_dist
            tp = price + tp_dist
        elif side == "SELL":
            sl = price + sl_dist
            tp = price - tp_dist
        else:
            # WAIT: ainda preenche níveis para a UI (planejamento)
            sl = price - sl_dist
            tp = price + tp_dist

        # Confiança (0..1): baseado no score normalizado e travado
        conf = min(1.0, max(0.0, abs(score) / (self.config.threshold + 2.0)))

        reason = f"trend={'UP' if trend>0 else 'DOWN'} | momentum={momentum:.2f} ATR | newsImpact={news_impact:.2f}"
        return Signal(
            symbol=symbol,
            side=side,
            price=price,
            sl=float(sl),
            tp=float(tp),
            confidence=float(conf),
            reason=reason,
            ts=datetime.utcnow(),
            meta={"ema_fast": float(e_fast), "ema_slow": float(e_slow), "atr": float(a), "score": float(score), "news_impact": float(news_impact)},
        )
