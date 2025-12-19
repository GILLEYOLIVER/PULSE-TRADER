from datetime import datetime, timezone
from trader_tool.domain.models import Signal, Side, RiskLimits
from trader_tool.risk.risk_manager import RiskManager

def test_position_sizing_basic():
    limits = RiskLimits(
        capital=10000, risk_per_trade_pct=1.0, max_daily_loss_pct=2.0,
        max_contracts=10, max_stops_in_row=3, cooldown_minutes=30,
        tick_value=1.0, tick_size=1.0, slippage_ticks=1
    )
    rm = RiskManager(limits)
    s = Signal(ts=datetime.now(timezone.utc), symbol="WIN", side=Side.BUY, confidence=0.8, rationale="x")
    approved = rm.approve(s, last_price=100000, atr=10)
    assert approved is not None
    assert approved.contracts >= 1
