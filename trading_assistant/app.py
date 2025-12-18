from __future__ import annotations

# Permite rodar diretamente: python trading_assistant/app.py
if __package__ in (None, "", "trading_assistant"):
    import sys
    from pathlib import Path
    this_file = Path(__file__).resolve()
    project_root = this_file.parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

import asyncio
import time
from dataclasses import asdict
from datetime import datetime
from random import random
from threading import Event
from typing import Optional

from trading_assistant.alerts.notifier import Notifier
from trading_assistant.config import TradingAssistantConfig
from trading_assistant.core.models import OrderRequest
from trading_assistant.core.state import MarketState, RiskState
from trading_assistant.data_feeds.market_stream import MockMarketConnector
from trading_assistant.data_feeds.news_stream import MultiSourceNewsConnector
from trading_assistant.execution.order_router import OrderRouter
from trading_assistant.infra.audit import AuditLogger
from trading_assistant.news_impact.scorer import NewsImpactScorer
from trading_assistant.risk.risk_engine import RiskEngine
from trading_assistant.risk.validator import TradeValidator
from trading_assistant.signals.engine import SignalEngine


def _emit(event_queue, event_type: str, payload: dict) -> None:
    if event_queue is None:
        return
    try:
        event_queue.put({"type": event_type, "ts": datetime.utcnow().isoformat(), "payload": payload})
    except Exception:
        pass


def _try_get_command(command_queue):
    if command_queue is None:
        return None
    try:
        return command_queue.get_nowait()
    except Exception:
        return None


def _mock_orderbook(price: float, levels: int = 12):
    tick = max(0.01, price * 0.0005)
    asks, bids = [], []
    for i in range(1, levels + 1):
        p_ask = price + tick * i
        p_bid = price - tick * i
        asks.append({"price": p_ask, "qty": max(1.0, (random() * 1000.0) // 1)})
        bids.append({"price": p_bid, "qty": max(1.0, (random() * 1000.0) // 1)})
    asks.sort(key=lambda x: x["price"])
    bids.sort(key=lambda x: x["price"], reverse=True)
    return {"asks": asks, "bids": bids}


async def run_market_pipeline(
    config: TradingAssistantConfig,
    runtime_seconds: int = 30,
    stop_event: Optional[Event] = None,
    event_queue=None,
    command_queue=None,
) -> None:
    notifier = Notifier(config.notifier)
    audit = AuditLogger(config.audit)

    market = MockMarketConnector(config.market_feed)
    news = MultiSourceNewsConnector(config.news_feed)

    state = MarketState()
    risk_state = RiskState()

    scorer = NewsImpactScorer(config.news_feed)

    risk = RiskEngine(config.risk)
    validator = TradeValidator(config.validator)
    engine = SignalEngine(config.signal_engine)
    router = OrderRouter(config.execution)

    start_ts = time.time()
    audit.info("pipeline_start", {"config": asdict(config)})
    _emit(event_queue, "status", {"running": True})

    async def market_loop():
        try:
            async for candle in market.stream_candles(stop_event=stop_event):
                if stop_event and stop_event.is_set():
                    break

                state.update_candle(candle)

                # spread/book mock (até plugar Profit)
                state.set_spread(candle.symbol, 0.05 + random() * 0.20)
                _emit(event_queue, "candle", asdict(candle))
                _emit(event_queue, "orderbook", {"symbol": candle.symbol, "book": _mock_orderbook(float(candle.close), levels=14)})

                # comandos da UI (ordem manual)
                cmd = _try_get_command(command_queue)
                if cmd and cmd.get("type") == "ORDER":
                    symbol = str(cmd.get("symbol", ""))
                    if symbol and symbol in state.last_price:
                        price = float(state.last_price[symbol])
                        order = OrderRequest(
                            symbol=symbol,
                            side=str(cmd.get("side", "BUY")).upper(),
                            qty=float(cmd.get("qty", 1.0)),
                            price=price,
                            sl=float(cmd.get("sl", price)),
                            tp=float(cmd.get("tp", price)),
                            ts=datetime.utcnow(),
                            confidence=float(cmd.get("confidence", 0.5)),
                            reason=str(cmd.get("reason", "manual_ui")),
                        )
                        if validator.is_trade_allowed(order, state, risk_state):
                            report = await router.execute(order, state)
                            audit.info("execution_report", asdict(report))
                            notifier.notify_execution(report)
                            _emit(event_queue, "execution", asdict(report))
                        else:
                            _emit(event_queue, "log", {"msg": f"Ordem bloqueada (spread/news): {symbol}"})

                # sinal automático (recomendação por ativo)
                sig = engine.generate_signal(state, symbol=candle.symbol)
                if sig is not None:
                    _emit(event_queue, "signal", asdict(sig))

                    sized = risk.size_position(sig, state, risk_state)
                    if sized is not None:
                        _emit(event_queue, "risk", asdict(risk_state))

                if time.time() - start_ts > runtime_seconds:
                    break

        except asyncio.CancelledError:
            return

    async def news_loop():
        try:
            batch = []
            last_score_emit = time.time()

            async for item in news.stream_news(stop_event=stop_event):
                if stop_event and stop_event.is_set():
                    break

                state.update_news(item)
                _emit(event_queue, "news", asdict(item))

                batch.append(item)
                # recalcula impacto a cada X segundos com os itens recentes coletados
                if time.time() - last_score_emit >= 5:
                    scores = scorer.score_items(batch[-120:])
                    for sym, sc in scores.items():
                        state.set_news_impact(sym, sc)
                        _emit(event_queue, "news_impact", {"symbol": sym, "score": sc})
                    last_score_emit = time.time()

                if time.time() - start_ts > runtime_seconds:
                    break

        except asyncio.CancelledError:
            return

    try:
        await asyncio.gather(market_loop(), news_loop())
    except asyncio.CancelledError:
        pass
    finally:
        audit.info("pipeline_end", {"runtime_seconds": runtime_seconds})
        _emit(event_queue, "status", {"running": False})


def main(runtime_seconds: int = 30) -> None:
    config = TradingAssistantConfig()
    try:
        asyncio.run(run_market_pipeline(config, runtime_seconds=runtime_seconds))
    except KeyboardInterrupt:
        print("\n[OK] Interrompido (Ctrl+C).")


if __name__ == "__main__":
    main(runtime_seconds=30)
