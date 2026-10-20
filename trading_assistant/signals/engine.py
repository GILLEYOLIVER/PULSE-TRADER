from __future__ import annotations

from datetime import datetime
from typing import Optional

from trading_assistant.config import SignalEngineConfig
from trading_assistant.core.models import Signal
from trading_assistant.core.state import MarketState
from trading_assistant.signals.technicals import atr, ema


class SignalEngine:
    """Motor explicável para BUY/SELL/WAIT (sem ML).

    Ideia:
    - Tendência: EMA rápida vs EMA lenta
    - Momento: distância do preço para EMA lenta em unidades de ATR
    - Penalidade: notícias fortes (puxa para WAIT)

    Stops curtos + alvos longos:
    - stop_dist = stop_atr_mult * ATR
    - target_dist = stop_dist * reward_r
    """

    def __init__(self, config: SignalEngineConfig) -> None:
        self.config = config

    def generate_signal(self, state: MarketState, symbol: str) -> Optional[Signal]:
        candles = state.get_last_candles(symbol, n=max(200, self.config.ema_slow + 20))
        if len(candles) < max(self.config.ema_slow + 2, self.config.atr_period + 2):
            return None

        closes = [float(c.close) for c in candles]
        price = float(closes[-1])

        e_fast = float(ema(closes, self.config.ema_fast))
        e_slow = float(ema(closes, self.config.ema_slow))
        a = float(atr(candles, self.config.atr_period))
        a = max(a, max(price * 0.0005, 0.01))  # evita ATR zero/absurdo

        trend = 1.0 if e_fast > e_slow else -1.0 if e_fast < e_slow else 0.0
        momentum = (price - e_slow) / max(a, 1e-9)  # em unidades de ATR (positivo = acima da EMA lenta)

        news_impact = float(state.news_impact.get(symbol, 0.0))
        # penaliza operar em notícias MUITO fortes (puxa para WAIT)
        news_penalty = min(2.0, max(0.0, news_impact / 2.5))

        raw_score = trend + momentum
        score = max(0.0, abs(raw_score) - news_penalty) * (1.0 if raw_score >= 0 else -1.0)

        side = "WAIT"
        if score >= float(self.config.threshold):
            side = "BUY"
        elif score <= -float(self.config.threshold):
            side = "SELL"

        # Stops curtos + alvos longos (R:R alto)
        sl_dist = float(self.config.stop_atr_mult) * a
        tp_dist = sl_dist * float(self.config.reward_r)

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

        # Confiança (0..1): baseado no score normalizado
        conf = min(1.0, max(0.0, abs(score) / (float(self.config.threshold) + 2.0)))

        # filtro extra (evita sinal fraco)
        if side in ("BUY", "SELL") and conf < float(self.config.min_confidence):
            side = "WAIT"

        reason = (
            f"trend={'UP' if trend > 0 else 'DOWN' if trend < 0 else 'FLAT'}"
            f" | momentum={momentum:.2f} ATR"
            f" | newsImpact={news_impact:.2f}"
            f" | score={score:.2f}"
            f" | RR={float(self.config.reward_r):.2f}"
        )

        return Signal(
            symbol=symbol,
            side=side,
            price=price,
            sl=float(sl),
            tp=float(tp),
            confidence=float(conf),
            reason=reason,
            ts=datetime.utcnow(),
            meta={
                "ema_fast": float(e_fast),
                "ema_slow": float(e_slow),
                "atr": float(a),
                "trend": float(trend),
                "momentum": float(momentum),
                "news_impact": float(news_impact),
                "news_penalty": float(news_penalty),
                "score": float(score),
                "stop_dist": float(sl_dist),
                "target_dist": float(tp_dist),
                "rr": float(self.config.reward_r),
            },
        )
