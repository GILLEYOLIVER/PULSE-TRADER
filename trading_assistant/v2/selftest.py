"""Offline checks shared by the portable executable and source distribution."""
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import time
from pathlib import Path


def run(output):
    result={'ok':False,'frozen':bool(getattr(sys,'frozen',False)),'mode':'PAPER','checks':[]}
    dashboard=None
    workspace=tempfile.TemporaryDirectory()
    try:
        from .dashboard import Dashboard
        directory=workspace.name
        dashboard=Dashboard(directory);dashboard.root.withdraw();dashboard.auto.set(False)
        for _ in range(80):dashboard.step()
        result['checks'].append('replay_80_closed_candles')
        panel=dashboard.suggestions;panel.load_demo()
        assert len(panel.rows)==2
        panel.profile.set('Dias e semanas · diário');panel.analyze();assert len(panel.rows)==2
        panel.store_selected();assert not dashboard.ledger.read()['orders']
        result['checks'].append('suggestions_profiles_and_proposal_without_orders')
        window=dashboard.open_settings();window.values[('limits','weekly_loss')].set('650');window.apply()
        assert dashboard.limits.weekly_loss==650
        result['checks'].append('settings_forms')
        from datetime import datetime,timedelta,timezone
        from .models import Bar
        start=datetime(2026,1,5,12,tzinfo=timezone.utc)
        rows=[Bar('WDO',start+timedelta(minutes=i),1000+i,1001+i,999+i,1000+i,10000.,'SYNTHETIC') for i in range(70)]
        panel.add_bars(rows);panel.profile.set('No dia · minutos e horas');panel.analyze()
        panel.load_selected_replay()
        deadline=time.monotonic()+10
        while panel.warming_up and time.monotonic()<deadline:
            dashboard.root.update();time.sleep(.01)
        assert not panel.warming_up and panel.selected().candles==70
        panel.arm_selected();assert panel.selected_plan()['state']=='ARMED'
        panel.cancel_selected();assert panel.selected_plan()['state']=='CANCELLED'
        result['checks'].append('catalog_to_replay_arm_and_cancel_plan')
        from .backups import create_backup,restore_backup
        backup=Path(directory)/'copy.zip';create_backup(directory,backup)
        restored=Path(directory)/'restored';restore_backup(backup,restored)
        assert (restored/'paper.sqlite').is_file()
        result['checks'].append('portable_backup_restore')
        done=[];dashboard.jobs.start(lambda:42,lambda value:done.append(value))
        deadline=time.monotonic()+5
        while dashboard.jobs.busy and time.monotonic()<deadline:
            dashboard.root.update();time.sleep(.01)
        assert done==[42]
        assert dashboard.ledger.db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        result['checks'].append('background_callbacks_and_embedded_sqlite')
        dashboard.close();dashboard=None

        result.update(ok=True,sqlite_version=sqlite3.sqlite_version,python=sys.version.split()[0])
    except Exception:
        import traceback
        result['error']=traceback.format_exc()
        if dashboard is not None:
            try:dashboard.close()
            except Exception:pass
    workspace.cleanup()
    path=Path(output);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(result,indent=2),encoding='utf-8')
    return 0 if result['ok'] else 1
