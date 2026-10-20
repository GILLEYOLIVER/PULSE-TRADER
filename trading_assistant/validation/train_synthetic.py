from __future__ import annotations

import argparse
import random
from dataclasses import asdict
from datetime import datetime, timezone, timedelta
from typing import List

from trading_assistant.config import TradingAssistantConfig
from trading_assistant.core.models import Candle
from trading_assistant.core.state import MarketState
from trading_assistant.signals.engine import SignalEngine
from trading_assistant.validation.performance import PerformanceTracker
from trading_assistant.validation.calibrator import OnlineCalibrator


def _gen_synthetic_candles(symbol: str, steps: int, tf_seconds: int) -> List[Candle]:
    """Gera candles sintéticos em regimes (trend/lateral/vol) sem olhar futuro.

    Isso treina o motor de forma honesta: ele só vê passado.
    """
    price = 100.0
    drift = 0.0
    vol = 0.8
    regime_left = 0

    out: List[Candle] = []
    ts = datetime.now(timezone.utc)

    for i in range(steps):
        # troca regime
        if regime_left <= 0:
            regime_left = random.randint(40, 200)
            regime = random.choice(["up", "down", "side"])
            if regime == "up":
                drift = random.uniform(0.02, 0.12)
            elif regime == "down":
                drift = -random.uniform(0.02, 0.12)
            else:
                drift = random.uniform(-0.02, 0.02)
            vol = random.uniform(0.4, 1.6)

        regime_left -= 1

        o = price
        # choque ocasional
        shock = 0.0
        if random.random() < 0.03:
            shock = random.uniform(-3.5, 3.5) * (vol / 1.0)

        change = drift + (random.random() - 0.5) * vol + shock
        c = max(0.01, o + change)
        h = max(o, c) + random.random() * (vol * 0.6)
        l = min(o, c) - random.random() * (vol * 0.6)

        price = c
        ts = ts + timedelta(seconds=tf_seconds)  # não precisa perfeição, é treino

        out.append(
            Candle(
                symbol=symbol,
                ts=ts,
                open=float(o),
                high=float(h),
                low=float(l),
                close=float(c),
                volume=float(100 + random.random() * 50),
            )
        )
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="WIN")
    ap.add_argument("--steps", type=int, default=20000)
    ap.add_argument("--tf", type=int, default=5, help="timeframe em segundos (simulado)")
    args = ap.parse_args()

    cfg = TradingAssistantConfig()
    cfg.market_feed.timeframe_seconds = int(args.tf)

    state = MarketState()
    engine = SignalEngine(cfg.signal_engine)
    tracker = PerformanceTracker(
        max_bars_in_trade=140,
        min_confidence_to_open=cfg.signal_engine.min_confidence,
        allow_flip=True,
    )
    calibrator = OnlineCalibrator(cfg.signal_engine, every_trades=10)

    candles = _gen_synthetic_candles(args.symbol, args.steps, int(args.tf))

    for c in candles:
        state.update_candle(c)
        # update trade with candle
        tracker.on_candle(c)
        # generate signal
        sig = engine.generate_signal(state, symbol=c.symbol)
        if sig is not None:
            tracker.on_signal(sig)
            rep = calibrator.maybe_calibrate(tracker)
            # silencioso: calibra ao longo

    snap = tracker.snapshot()
    print("\n=== RESULTADO TREINO SINTÉTICO ===")
    print(f"Trades: {snap.trades} | WinRate: {snap.win_rate*100:.1f}% | AvgR: {snap.avg_r:.3f} | PF: {snap.profit_factor:.2f} | MaxDD(R): {snap.max_dd_r:.2f}")
    print("\n=== PARÂMETROS AJUSTADOS ===")
    print(f"threshold={cfg.signal_engine.threshold:.2f}")
    print(f"stop_atr_mult={cfg.signal_engine.stop_atr_mult:.2f}")
    print(f"reward_r={cfg.signal_engine.reward_r:.2f}")
    print(f"min_confidence={cfg.signal_engine.min_confidence:.2f}")


if __name__ == "__main__":
    main()
