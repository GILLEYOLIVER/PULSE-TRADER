from __future__ import annotations
import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

from trader_tool.pipeline.bus import EventBus
from trader_tool.pipeline.aggregator import TickAggregator
from trader_tool.domain.models import Tick, Signal, ApprovedTrade, Side, RiskLimits
from trader_tool.strategies.momentum import MomentumStrategy
from trader_tool.strategies.orderflow import OrderflowStrategy
from trader_tool.strategies.breakout import BreakoutStrategy
from trader_tool.risk.risk_manager import RiskManager
from trader_tool.execution.paper import PaperBroker, PaperConfig
from trader_tool.alerts.notifier import LogNotifier, Alert
from trader_tool.storage.postgres import PostgresStore

logger = logging.getLogger("pulse.engine")

@dataclass
class EngineStatus:
    running: bool = False
    last_tick: Optional[Tick] = None
    last_signal: Optional[Signal] = None
    last_trade: Optional[ApprovedTrade] = None
    mode: str = "PAPER"
    diagnostics: str = ""

class TradingEngine:
    def __init__(self, *, bus: EventBus, symbols: list[str], settings, status_cb=None):
        self.bus = bus
        self.symbols = symbols
        self.settings = settings
        self.status_cb = status_cb
        self.status = EngineStatus(mode=settings.MODE)

        self.agg = TickAggregator(seconds=settings.TICK_AGG_SECONDS, window=240)
        self.notifier = LogNotifier()

        self.store: Optional[PostgresStore] = None
        if settings.PG_DSN:
            self.store = PostgresStore(settings.PG_DSN)
            self.store.ensure_schema()

        limits = RiskLimits(
            capital=settings.CAPITAL,
            risk_per_trade_pct=settings.RISK_PER_TRADE_PCT,
            max_daily_loss_pct=settings.MAX_DAILY_LOSS_PCT,
            max_contracts=settings.MAX_CONTRACTS,
            max_stops_in_row=settings.MAX_STOPS_IN_ROW,
            cooldown_minutes=settings.COOLDOWN_MINUTES,
            tick_value=settings.TICK_VALUE,
            tick_size=settings.TICK_SIZE,
            slippage_ticks=settings.SLIPPAGE_TICKS
        )
        self.risk = RiskManager(limits=limits)
        self.paper = PaperBroker(PaperConfig(slippage_ticks=settings.SLIPPAGE_TICKS, tick_size=settings.TICK_SIZE))

        self.strategies = [
            MomentumStrategy(),
            OrderflowStrategy(),
            BreakoutStrategy(),
        ]

        self._news_risk: dict[str, float] = {s: 0.0 for s in symbols}
        self._stop = asyncio.Event()
        self._last_wait_emit: dict[str, float] = {s: 0.0 for s in symbols}

    def _push_status(self):
        if self.status_cb:
            try:
                self.status_cb(self.status, self.risk.state)
            except Exception:
                pass

    async def stop(self):
        self._stop.set()

    async def run(self):
        self.status.running = True
        self._push_status()
        logger.info("Engine iniciada", extra={"symbols": self.symbols, "mode": self.settings.MODE})
        tick_task = asyncio.create_task(self._tick_loop())
        await self._stop.wait()
        tick_task.cancel()
        self.status.running = False
        self._push_status()
        logger.info("Engine parada")

    def _diag(self, tick: Tick, atr: float, imb: float) -> str:
        rs = self.risk.state
        cd = "SIM" if (rs.cooldown_until and tick.ts < rs.cooldown_until) else "NÃO"
        return f"ATR={atr:.2f} | NewsRisk={self._news_risk.get(tick.symbol, 0.0):.2f} | Imb={imb:.2f} | PnLHoje={rs.pnl_today:.2f} | StopsSeq={rs.stops_in_row} | Cooldown={cd}"

    async def _tick_loop(self):
        async for tick in self.bus.subscribe("ticks"):
            if self._stop.is_set():
                return

            self.status.last_tick = tick
            self.agg.push_tick(tick)

            imb = 0.0
            if tick.bid_size and tick.ask_size and (tick.bid_size + tick.ask_size) > 0:
                imb = (tick.bid_size - tick.ask_size) / (tick.bid_size + tick.ask_size)

            f = self.agg.compute_features(
                symbol=tick.symbol,
                now=tick.ts,
                last_price=tick.price,
                book_imbalance=imb,
                news_risk=self._news_risk.get(tick.symbol, 0.0)
            )

            self.status.diagnostics = self._diag(tick, f.atr, imb)

            best: Signal | None = None
            for strat in self.strategies:
                s = strat.on_features(f)
                if s is None:
                    continue
                if best is None or s.confidence > best.confidence:
                    best = s

            if best is None:
                # explica WAIT 1x por segundo
                now_s = tick.ts.timestamp()
                if now_s - self._last_wait_emit.get(tick.symbol, 0.0) > 1.0:
                    self._last_wait_emit[tick.symbol] = now_s
                    best = Signal(ts=tick.ts, symbol=tick.symbol, side=Side.WAIT, confidence=0.55,
                                  rationale="Sem oportunidade clara (WAIT).", meta={"diag": self.status.diagnostics})

            if best:
                self.status.last_signal = best
                self._push_status()
                if self.store:
                    self.store.save_signal(best)

                approved = self.risk.approve(best, last_price=tick.price, atr=f.atr)

                if approved:
                    self.status.last_trade = approved
                    self._push_status()
                    if self.store:
                        self.store.save_approved(approved)

                    if self.settings.MODE in ("PAPER", "SIM"):
                        fill = self.paper.execute(approved, now=tick.ts, last_price=tick.price)
                        if self.store:
                            self.store.save_fill(fill)
                        self.paper.mark_to_market(tick.symbol, tick.price, self.settings.TICK_VALUE)
                        self.risk.update_pnl(tick.ts, realized_pnl=0.0, was_stop=False)
                        if self.store:
                            self.store.save_pnl_event(tick.ts, tick.symbol, realized_pnl=0.0, was_stop=False)

                    msg = (
                        f"{best.side.value} {best.symbol} | conf={best.confidence:.2f} | "
                        f"contratos={approved.contracts} | stop={approved.stop_price:.2f} | alvo={approved.target_price:.2f}\n"
                        f"Motivo: {best.rationale}"
                    )
                    self.notifier.send(Alert(title="SINAL APROVADO", message=msg, level="INFO"))
                else:
                    if best.side in (Side.BUY, Side.SELL):
                        self.status.last_trade = None
                        self.status.diagnostics += " | Risk=BLOQUEOU (sem contratos/limite/cooldown)"
                        self._push_status()

            self._push_status()
