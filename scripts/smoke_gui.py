import tempfile
from pathlib import Path
from trading_assistant.v2.dashboard import Dashboard
with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as tmp:
    d=Dashboard(tmp)
    d.root.withdraw()
    for _ in range(80): d.step()
    d.zoom(.8);d.pan(10);d.toggle_theme();d.timeframe.set('5 min');d.draw()
    d.emergency(True);assert d.ledger.read()['emergency']
    d.root.update_idletasks();d.root.update()
    print('GUI_OK: built, 80 bars, chart, zoom, pan, theme, timeframe, emergency')
    d.close()
