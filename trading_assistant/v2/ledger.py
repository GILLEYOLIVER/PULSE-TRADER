from __future__ import annotations
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

class Ledger:
    """Single-writer transactions, durable idempotency, no untrusted pickle files."""
    def __init__(self,path=":memory:"):
        if path!=":memory:": Path(path).parent.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(path,timeout=10)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("CREATE TABLE IF NOT EXISTS state(id INTEGER PRIMARY KEY CHECK(id=1),payload TEXT NOT NULL)")
        self.db.execute("CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,ts TEXT,event TEXT,payload TEXT)")
        self.db.execute("INSERT OR IGNORE INTO state VALUES(1,?)",(json.dumps({"version":1,"orders":{},"positions":{},"trades":[],"marks":{},"last_bars":{},"last_sources":{},"last_ohlcv":{},"blocks":{},"emergency":False,"connected":True,"cooldown_until":None,"loss_streak":0,"sequence":0}),))
        self.db.commit()
        self.read()  # corrupt/unsupported state fails closed

    def read(self):
        s=json.loads(self.db.execute("SELECT payload FROM state WHERE id=1").fetchone()[0])
        if s.get("version")!=1 or not all(k in s for k in ("orders","positions","trades","blocks","marks","emergency")):
            raise ValueError("Unsupported or corrupt ledger; reconcile before trading")
        return s

    @contextmanager
    def transaction(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            s=self.read()
            yield s
            self.db.execute("UPDATE state SET payload=? WHERE id=1",(json.dumps(s,allow_nan=False),))
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise

    def audit(self,ts,event,payload):
        self.db.execute("INSERT INTO audit(ts,event,payload) VALUES(?,?,?)",(str(ts),event,json.dumps(payload,allow_nan=False)))

    def close(self): self.db.close()


class SimulationLedger:
    """Disposable backtest state. Any failure invalidates the entire run.

    Never used by the desktop PAPER session. No database roundtrip or copies per
    candle: the runner exclusively owns this state. Failed runs cannot be read,
    resumed or committed, so partially applied decisions never become a report.
    """
    def __init__(self):
        seed=Ledger()
        try:self._state=seed.read()
        finally:seed.close()
        self._valid=True;self._active=False

    def read(self):
        if not self._valid:raise ValueError('Failed simulation must be discarded')
        return self._state

    @contextmanager
    def transaction(self):
        self.read()
        if self._active:raise ValueError('Nested simulation transaction')
        self._active=True
        try:yield self._state
        except BaseException:
            self._valid=False
            raise
        finally:self._active=False

    def audit(self,ts,event,payload):
        self.read()  # Backtest orders/trades preserve outcomes; no durable audit writes.

    def close(self):self._valid=False
