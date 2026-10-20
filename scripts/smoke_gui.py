import json
import os
import tempfile
from unittest.mock import patch
from pathlib import Path
from trading_assistant.v2.dashboard import Dashboard
from trading_assistant.v2.data import export_csv
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
    panel=d.suggestions
    panel.demo_button.invoke()
    assert {s.symbol for s in panel.rows.values()}=={'WIN','WDO'}
    panel.profile.set('Dias e semanas · diário');panel.analyze()
    assert {s.symbol for s in panel.rows.values()}=={'PETR4','VALE3'}
    assert all(s.seconds==86400 for s in panel.rows.values())
    assert 'Motivo:' in panel.detail.get('1.0','end')
    before=d.ledger.read()['orders']
    panel.save_button.invoke()
    saved=d.ledger.read()
    assert len(saved['analysis_plans'])==1 and saved['orders']==before
    assert not next(iter(saved['analysis_plans'].values()))['risk_approved']
    # Import two profiles together, then reload the durable catalog.
    paths=[]
    for i,bars in enumerate(panel.series.values()):
        path=Path(tmp)/f'suggestions-{i}.csv';export_csv(bars,path);paths.append(str(path))
    with patch('trading_assistant.v2.suggestions_ui.filedialog.askopenfilenames',return_value=paths):
        panel.import_button.invoke()
    panel.series={};panel.load_catalog()
    assert {s.symbol for s in panel.rows.values()}=={'PETR4','VALE3'}
    panel.replay_button.invoke()
    assert len(panel.rows)==1 and panel.selected().candles==80
    assert panel.selected().closed_at==d.now()
    suggestions_path=Path(tmp)/'suggestions.json'
    with patch('trading_assistant.v2.suggestions_ui.filedialog.asksaveasfilename',return_value=str(suggestions_path)):
        panel.export()
    assert json.loads(suggestions_path.read_text(encoding='utf-8'))['analyses'][0]['confidence'] is None
    d.zoom(.8);d.pan(10);d.toggle_theme();d.timeframe.set('5 min');d.draw()
    d.emergency(True);assert d.ledger.read()['emergency']
    d.root.update_idletasks();d.root.update()
    screenshot=os.getenv('PULSE_SMOKE_SCREENSHOT')
    if screenshot:
        from PIL import ImageGrab
        panel.load_demo();d.tabs.select(panel.frame)
        d.status.set('PAPER | Sugestões com dados SYNTHETIC | Exemplo sem cotação ao vivo')
        d.root.deiconify();d.root.lift();d.root.attributes('-topmost',True)
        d.root.update_idletasks();d.root.update()
        assert panel.save_button.winfo_height()>20
        x,y=d.root.winfo_rootx(),d.root.winfo_rooty()
        image=ImageGrab.grab(bbox=(x,y,x+d.root.winfo_width(),y+d.root.winfo_height()))
        Path(screenshot).parent.mkdir(parents=True,exist_ok=True);image.save(screenshot)
    print('GUI_OK: risk form, calendar, UI backtest, suggestions intraday/swing, saved plan, multi-CSV catalog, replay cutoff, export, chart, theme, emergency')
    d.close()
