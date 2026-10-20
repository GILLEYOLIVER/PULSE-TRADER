import json
import tempfile
from unittest.mock import patch
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
    settings=json.loads(d.settings_text.get('1.0','end'))
    settings['calendar']={'holidays':['2026-01-05'],'start':'09:00:00','end':'18:00:00','verified':True}
    d.settings_text.delete('1.0','end')
    d.settings_text.insert('1.0',json.dumps(settings))
    d.apply_settings()
    assert d.engine.calendar.to_config()==settings['calendar']
    for _ in range(80): d.step()
    d.feed=d.feed[:80]
    report_path=Path(tmp)/'ui-backtest.json'
    with patch('trading_assistant.v2.dashboard.filedialog.asksaveasfilename',return_value=str(report_path)):
        d.backtest()
    report=json.loads(report_path.read_text(encoding='utf-8'))
    assert report['calendar']==settings['calendar']
    assert not any(order['filled_qty'] for order in report['orders'])
    d.zoom(.8);d.pan(10);d.toggle_theme();d.timeframe.set('5 min');d.draw()
    d.emergency(True);assert d.ledger.read()['emergency']
    d.root.update_idletasks();d.root.update()
    print('GUI_OK: risk form, calendar, UI backtest calendar, 80 bars, chart, zoom, pan, theme, timeframe, emergency')
    d.close()
