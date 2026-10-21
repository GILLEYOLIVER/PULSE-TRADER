import json
import os
import time
import tempfile
from unittest.mock import patch
from pathlib import Path
from trading_assistant.v2.dashboard import Dashboard
from trading_assistant.v2.data import export_csv
from tkinter import ttk

def assert_readable(root,foreground,background):
    def luminance(color):
        rgb=[v/65535 for v in root.winfo_rgb(color)]
        linear=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in rgb]
        return sum(v*w for v,w in zip(linear,(.2126,.7152,.0722)))
    lo,hi=sorted((luminance(foreground),luminance(background)))
    assert (hi+.05)/(lo+.05)>=4.5,(foreground,background)

with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as tmp:
    d=Dashboard(tmp)
    d.root.withdraw()
    for dark in (True,False,True):
        d.dark=dark;d._theme();style=ttk.Style(d.root)
        for name,fg,bg,states in (
                ('TEntry','foreground','fieldbackground',((),('disabled',),('readonly',))),
                ('TCombobox','foreground','fieldbackground',((),('readonly',),('disabled',))),
                ('TEntry','selectforeground','selectbackground',((),)),
                ('Badge.TLabel','foreground','background',((),)),
                ('Accent.TButton','foreground','background',((),('active',),('pressed',))),
                ('Treeview','foreground','background',(('selected',),))):
            for state in states:
                foreground=style.lookup(name,fg,state);background=style.lookup(name,bg,state)
                assert foreground and background,(name,state,'Missing field colors')
                assert_readable(d.root,foreground,background)
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
    deadline=time.monotonic()+15
    while d.jobs.busy and time.monotonic()<deadline:
        d.root.update();time.sleep(.01)
    assert not d.jobs.busy
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
    print('GUI_OK: readable inputs/selections/buttons in both themes, risk form, calendar, UI backtest, suggestions intraday/swing, saved plan, multi-CSV catalog, replay cutoff, export, chart, theme, emergency')
    d.close()

# A seconds demo survives restart and chart interactions never submit orders.
with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as tmp:
    d=Dashboard(tmp);d.root.withdraw();d.auto.set(False)
    d.load_synthetic(seconds=1)
    assert tuple(d._period_seconds.values())[:5]==(1,5,10,15,30)
    assert d.timeframe.get()=='1 s'
    for _ in range(40):d.step()
    assert all(b.seconds==1 for b in d.bars) and not d.ledger.read()['orders']
    from trading_assistant.v2.learning import digest
    before=digest(d.ledger.read())
    for _ in range(12):d.zoom(.85);d.zoom(1.2)
    d.timeframe.set('15 s');d.change_period()
    deadline=time.monotonic()+2
    while (d._chart_after or d._chart_quality_after) and time.monotonic()<deadline:
        d.root.update();time.sleep(.005)
    assert d._chart_after is None and d._chart_quality_after is None
    assert digest(d.ledger.read())==before
    original_feed=d.feed.copy();d.close()
    d=Dashboard(tmp);d.root.withdraw()
    assert d.feed==original_feed and d.cursor==40 and d.timeframe.get()=='1 s'
    assert all(b.seconds==1 for b in d.bars)
    d.load_synthetic()
    assert d.feed[0].ts.second==0 and d.timeframe.get()=='1 min'
    d.close()
    print('GUI_SECONDS_OK: closed1s demo, 5/10/15/30s views, queued zoom, unchanged ledger, restart and aligned new demo')
