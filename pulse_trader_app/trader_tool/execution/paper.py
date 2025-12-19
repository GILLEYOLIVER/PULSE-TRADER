from __future__ import annotations
from dataclasses import dataclass
from trader_tool.domain.models import ApprovedTrade, Fill, Side, Position
from datetime import datetime

@dataclass
class PaperConfig:
    slippage_ticks: int = 1
    tick_size: float = 1.0
    fee_per_contract: float = 0.0

class PaperBroker:
    """Executa no papel: entra imediatamente no próximo tick com slippage."""
    def __init__(self, cfg: PaperConfig):
        self.cfg = cfg
        self.positions: dict[str, Position] = {}

    def _pos(self, symbol: str) -> Position:
        if symbol not in self.positions:
            self.positions[symbol] = Position(symbol=symbol)
        return self.positions[symbol]

    def execute(self, trade: ApprovedTrade, now: datetime, last_price: float) -> Fill:
        slip = self.cfg.slippage_ticks * self.cfg.tick_size
        price = last_price + slip if trade.side == Side.BUY else last_price - slip
        fees = self.cfg.fee_per_contract * trade.contracts
        fill = Fill(ts=now, symbol=trade.symbol, side=trade.side, contracts=trade.contracts, price=price, fees=fees)
        self._apply_fill(fill)
        return fill

    def mark_to_market(self, symbol: str, last_price: float, tick_value: float):
        pos = self._pos(symbol)
        pos.last_price = last_price
        if pos.contracts != 0:
            # pnl = (price - avg) * contracts * tick_value (sinal do contracts)
            pos.unrealized_pnl = (last_price - pos.avg_price) * pos.contracts * tick_value
        else:
            pos.unrealized_pnl = 0.0

    def _apply_fill(self, fill: Fill):
        pos = self._pos(fill.symbol)
        signed = fill.contracts if fill.side == Side.BUY else -fill.contracts

        # se posição zera ou inverte, realiza pnl sobre parte fechada
        if pos.contracts == 0:
            pos.contracts = signed
            pos.avg_price = fill.price
            return

        # mesma direção: recalcula preço médio
        if (pos.contracts > 0 and signed > 0) or (pos.contracts < 0 and signed < 0):
            new_qty = pos.contracts + signed
            if new_qty == 0:
                pos.contracts = 0
                pos.avg_price = 0.0
            else:
                pos.avg_price = (pos.avg_price * abs(pos.contracts) + fill.price * abs(signed)) / abs(new_qty)
                pos.contracts = new_qty
            return

        # direção oposta: fecha parcial/total
        close_qty = min(abs(pos.contracts), abs(signed))
        # pnl realizado para a parte fechada
        if pos.contracts > 0:  # estava comprado, vendendo fecha
            pnl = (fill.price - pos.avg_price) * close_qty
        else:  # estava vendido, comprando fecha
            pnl = (pos.avg_price - fill.price) * close_qty

        pos.realized_pnl += pnl
        # atualiza quantidade restante
        remaining = abs(pos.contracts) - close_qty
        if remaining == 0:
            pos.contracts = 0
            pos.avg_price = 0.0
        else:
            pos.contracts = remaining if pos.contracts > 0 else -remaining
