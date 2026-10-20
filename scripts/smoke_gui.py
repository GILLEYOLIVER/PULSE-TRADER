import tempfile
from pathlib import Path
from trading_assistant.v2.dashboard import Dashboard
with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as tmp:
    d=Dashboard(tmp)
    d.root.withdraw()
    d.quick_vars['capital'].set('12000')
    d.quick_vars['risk_percent'].set('0,4')
    d.quick_vars['strategy'].set('breakout')
    d.apply_quick_settings()
    assert d.ledger.read()['config']['limits']['capital']==12000
    assert d.ledger.read()['config']['limits']['risk_fraction']==.004
    assert d.engine.strategy.name=='breakout'
    for _ in range(80): d.step()
    d.zoom(.8);d.pan(10);d.toggle_theme();d.timeframe.set('5 min');d.draw()
    d.emergency(True);assert d.ledger.read()['emergency']
    d.root.update_idletasks();d.root.update()
    print('GUI_OK: risk form, 80 bars, chart, zoom, pan, theme, timeframe, emergency')
    d.close()
