from __future__ import annotations
import math
from trading_assistant.v2.models import INSTRUMENTS

class RiskEngine:
    """Compatibility sizing for legacy recommendations; execution requires v2."""
    def __init__(self,config): self.config=config
    def daily_limits_ok(self,risk_state):
        return risk_state.trades_today<self.config.max_trades_per_day and risk_state.pnl_today>-self.config.capital*self.config.max_daily_loss
    def size_position(self,signal,state,risk_state):
        from trading_assistant.core.models import OrderRequest
        spec=INSTRUMENTS.get(signal.symbol)
        if not spec or signal.side not in ("BUY","SELL") or not self.daily_limits_ok(risk_state): return None
        values=(signal.price,signal.sl,signal.tp,self.config.capital,self.config.risk_per_trade)
        if not all(math.isfinite(v) and v>0 for v in values):return None
        direction=1 if signal.side=="BUY" else -1
        if (signal.price-signal.sl)*direction<=0 or (signal.tp-signal.price)*direction<=0:return None
        qty=math.floor(self.config.capital*self.config.risk_per_trade/(abs(signal.price-signal.sl)*spec.point_value)/spec.lot)*spec.lot
        if qty<spec.lot:return None
        return OrderRequest(signal.symbol,signal.side,float(qty),signal.price,signal.sl,signal.tp,signal.ts,signal.confidence,signal.reason)
