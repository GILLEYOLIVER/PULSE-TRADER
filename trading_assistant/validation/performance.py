from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone

from trading_assistant.core.models import Candle, Signal


@dataclass
class ShadowTrade:
    symbol: str
    side: str  # BUY/SELL
    entry_price: float
    sl: float
    tp: float
    confidence: float
    opened_at: datetime
    opened_bar: int
    reason: str = ""
    meta: Dict[str, float] = field(default_factory=dict)

    exit_price: Optional[float] = None
    exit_reason: Optional[str] = None  # TP/SL/TIME/FLIP
    closed_at: Optional[datetime] = None
    closed_bar: Optional[int] = None

    def is_open(self) -> bool:
        return self.exit_price is None

    def risk_per_unit(self) -> float:
        # risco por unidade (sempre positivo)
        if self.side == "BUY":
            return max(1e-9, self.entry_price - self.sl)
        return max(1e-9, self.sl - self.entry_price)

    def r_multiple(self) -> Optional[float]:
        if self.exit_price is None:
            return None
        risk = self.risk_per_unit()
        if self.side == "BUY":
            pnl = self.exit_price - self.entry_price
        else:
            pnl = self.entry_price - self.exit_price
        return pnl / risk


@dataclass
class PerformanceSnapshot:
    trades: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    avg_r: float = 0.0
    profit_factor: float = 0.0
    max_dd_r: float = 0.0  # drawdown em R
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class PerformanceTracker:
    """Shadow trading (paper automático) para treinar e medir o motor.

    - Abre 1 posição por símbolo quando chega sinal BUY/SELL.
    - Fecha em TP/SL usando OHLC (conservador quando toca os dois no mesmo candle).
    - Opcional: fecha por tempo (max_bars).
    - Retorna eventos para a UI: open/update/close + snapshot.
    """

    def __init__(
        self,
        max_bars_in_trade: int = 120,
        min_confidence_to_open: float = 0.55,
        allow_flip: bool = True,
    ) -> None:
        self.max_bars_in_trade = int(max(10, max_bars_in_trade))
        self.min_confidence_to_open = float(min_confidence_to_open)
        self.allow_flip = bool(allow_flip)

        self._bar_index: Dict[str, int] = {}
        self.open_trades: Dict[str, ShadowTrade] = {}
        self.closed_trades: List[ShadowTrade] = []

        # curva em R para drawdown
        self._equity_r: float = 0.0
        self._peak_r: float = 0.0
        self._max_dd_r: float = 0.0

    def bar_index(self, symbol: str) -> int:
        return int(self._bar_index.get(symbol, 0))

    def on_candle(self, candle: Candle) -> List[Tuple[str, dict]]:
        """Atualiza posições abertas e pode fechar trade."""
        sym = candle.symbol
        self._bar_index[sym] = self._bar_index.get(sym, 0) + 1

        evs: List[Tuple[str, dict]] = []
        trade = self.open_trades.get(sym)
        if trade is None:
            return evs

        # checa encerramento por SL/TP usando OHLC do candle
        o = float(candle.open)
        h = float(candle.high)
        l = float(candle.low)
        c = float(candle.close)

        hit_tp = False
        hit_sl = False

        if trade.side == "BUY":
            hit_tp = h >= trade.tp
            hit_sl = l <= trade.sl
            tp_price = trade.tp
            sl_price = trade.sl
        else:  # SELL
            hit_tp = l <= trade.tp
            hit_sl = h >= trade.sl
            tp_price = trade.tp
            sl_price = trade.sl

        # conservador: se bateu os dois, considera SL primeiro
        if hit_sl and hit_tp:
            self._close(trade, sl_price, "SL", candle.ts, self._bar_index[sym])
            evs.append(("shadow_trade", self._trade_payload(trade)))
            self.open_trades.pop(sym, None)
            evs.append(("shadow_position", {"symbol": sym, "status": "flat"}))
            return evs

        if hit_sl:
            self._close(trade, sl_price, "SL", candle.ts, self._bar_index[sym])
            evs.append(("shadow_trade", self._trade_payload(trade)))
            self.open_trades.pop(sym, None)
            evs.append(("shadow_position", {"symbol": sym, "status": "flat"}))
            return evs

        if hit_tp:
            self._close(trade, tp_price, "TP", candle.ts, self._bar_index[sym])
            evs.append(("shadow_trade", self._trade_payload(trade)))
            self.open_trades.pop(sym, None)
            evs.append(("shadow_position", {"symbol": sym, "status": "flat"}))
            return evs

        # tempo máximo
        if (self._bar_index[sym] - trade.opened_bar) >= self.max_bars_in_trade:
            self._close(trade, c, "TIME", candle.ts, self._bar_index[sym])
            evs.append(("shadow_trade", self._trade_payload(trade)))
            self.open_trades.pop(sym, None)
            evs.append(("shadow_position", {"symbol": sym, "status": "flat"}))
            return evs

        # ainda aberto: manda update leve (pra UI desenhar linhas SL/TP)
        evs.append(("shadow_position", self._position_payload(trade, candle)))
        return evs

    def on_signal(self, signal: Signal) -> List[Tuple[str, dict]]:
        sym = signal.symbol
        side = str(signal.side).upper()
        if side not in ("BUY", "SELL"):
            return []

        conf = float(signal.confidence or 0.0)
        if conf < self.min_confidence_to_open:
            return []

        evs: List[Tuple[str, dict]] = []
        cur = self.open_trades.get(sym)

        # se já tem trade aberto: opcional flip
        if cur is not None:
            if not self.allow_flip:
                return []
            if cur.side != side:
                # fecha e abre novo
                now = signal.ts
                px = float(signal.price)
                self._close(cur, px, "FLIP", now, self._bar_index.get(sym, 0))
                evs.append(("shadow_trade", self._trade_payload(cur)))
                self.open_trades.pop(sym, None)
            else:
                return []  # mesmo lado, ignora

        trade = ShadowTrade(
            symbol=sym,
            side=side,
            entry_price=float(signal.price),
            sl=float(signal.sl),
            tp=float(signal.tp),
            confidence=float(signal.confidence),
            opened_at=signal.ts,
            opened_bar=self._bar_index.get(sym, 0),
            reason=str(signal.reason or ""),
            meta={k: float(v) for k, v in (signal.meta or {}).items() if _is_number(v)},
        )
        self.open_trades[sym] = trade

        evs.append(("shadow_position", {"symbol": sym, "status": "open", **self._position_payload(trade, None)}))
        return evs

    def snapshot(self) -> PerformanceSnapshot:
        tr = self.closed_trades
        trades = len(tr)
        wins = sum(1 for t in tr if (t.r_multiple() or 0.0) > 0)
        losses = trades - wins
        win_rate = (wins / trades) if trades else 0.0

        rs = [t.r_multiple() or 0.0 for t in tr]
        avg_r = (sum(rs) / trades) if trades else 0.0

        pos_sum = sum(r for r in rs if r > 0)
        neg_sum = abs(sum(r for r in rs if r < 0))
        profit_factor = (pos_sum / neg_sum) if neg_sum > 1e-9 else (pos_sum if trades else 0.0)

        snap = PerformanceSnapshot(
            trades=trades,
            wins=wins,
            losses=losses,
            win_rate=float(win_rate),
            avg_r=float(avg_r),
            profit_factor=float(profit_factor),
            max_dd_r=float(self._max_dd_r),
            last_updated=datetime.now(timezone.utc),
        )
        return snap

    # -------- internals --------
    def _close(self, trade: ShadowTrade, exit_price: float, reason: str, ts: datetime, bar: int) -> None:
        trade.exit_price = float(exit_price)
        trade.exit_reason = str(reason)
        trade.closed_at = ts
        trade.closed_bar = int(bar)

        self.closed_trades.append(trade)

        r = trade.r_multiple() or 0.0
        self._equity_r += r
        self._peak_r = max(self._peak_r, self._equity_r)
        dd = self._peak_r - self._equity_r
        self._max_dd_r = max(self._max_dd_r, dd)

    def _trade_payload(self, trade: ShadowTrade) -> dict:
        r = trade.r_multiple()
        return {
            "symbol": trade.symbol,
            "side": trade.side,
            "entry": trade.entry_price,
            "sl": trade.sl,
            "tp": trade.tp,
            "confidence": trade.confidence,
            "opened_at": _fmt(trade.opened_at),
            "exit": trade.exit_price,
            "exit_reason": trade.exit_reason,
            "closed_at": _fmt(trade.closed_at) if trade.closed_at else None,
            "r_multiple": float(r) if r is not None else None,
            "reason": trade.reason,
        }

    def _position_payload(self, trade: ShadowTrade, candle: Optional[Candle]) -> dict:
        last = float(candle.close) if candle else trade.entry_price
        return {
            "symbol": trade.symbol,
            "side": trade.side,
            "entry": trade.entry_price,
            "sl": trade.sl,
            "tp": trade.tp,
            "confidence": trade.confidence,
            "last": last,
            "opened_at": _fmt(trade.opened_at),
        }


def _fmt(dt: Optional[datetime]) -> str:
    if not dt:
        return ""
    try:
        return dt.astimezone(timezone.utc).strftime("%H:%M:%S")
    except Exception:
        return str(dt)


def _is_number(x) -> bool:
    try:
        float(x)
        return True
    except Exception:
        return False
