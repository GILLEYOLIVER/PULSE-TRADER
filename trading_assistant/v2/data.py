from __future__ import annotations

import csv
import hashlib
import json
import random
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, Protocol

from .models import Bar, UTC, aware

class DataProvider(Protocol):
    def bars(self) -> Iterable[Bar]: ...

class CSVProvider:
    """User-authorized historical data. Each row explicitly identifies its source."""
    def __init__(self,path: str|Path):
        self.path = Path(path)
        self.sha256 = hashlib.sha256(self.path.read_bytes()).hexdigest()

    def bars(self) -> list[Bar]:
        out, seen = [], set()
        with self.path.open(encoding="utf-8-sig",newline="") as f:
            for row in csv.DictReader(f):
                b = Bar(row["symbol"].upper(),aware(datetime.fromisoformat(row["ts"])),
                        *(float(row[k]) for k in ("open","high","low","close","volume")),
                        row["source"],int(row.get("seconds") or 60))
                key=(b.symbol,b.ts)
                if key in seen: raise ValueError("Duplicate candle")
                seen.add(key)
                out.append(b)
        if not out: raise ValueError("Empty CSV")
        # Preserve input order; never silently repair lookahead or timestamp errors.
        previous={};metadata={}
        for b in out:
            if b.symbol in previous and b.ts < previous[b.symbol]: raise ValueError("Unsorted or overlapping candles")
            series=(b.source,b.seconds)
            if b.symbol in metadata and metadata[b.symbol]!=series:
                raise ValueError("Mixed source or timeframe for symbol")
            metadata[b.symbol]=series
            previous[b.symbol] = b.ts+timedelta(seconds=b.seconds)
        return sorted(out,key=lambda b:(b.ts,b.symbol))

class SyntheticProvider:
    def __init__(self,symbol="WIN",count=1000,seed=42,seconds=60,start=None):
        if count < 1 or seconds < 1: raise ValueError("Invalid feed dimensions")
        self.symbol,self.count,self.seed,self.seconds=symbol,count,seed,seconds
        self.start=start or datetime(2026,1,5,12,tzinfo=UTC)

    def bars(self) -> list[Bar]:
        rng=random.Random(self.seed)
        base={"WIN":130000.,"IND":130000.,"WDO":5500.,"DOL":5500.,"BTC":350000.,"ETH":15000.}.get(self.symbol,40.)
        price=base
        out=[]
        for i in range(self.count):
            drift=(1 if (i//120)%3==0 else -1 if (i//120)%3==1 else 0)*base*.00007
            delta=drift+rng.gauss(0,base*.0003)
            close=max(.01,price+delta)
            out.append(Bar(self.symbol,self.start+timedelta(seconds=i*self.seconds),price,
                max(price,close)+rng.random()*base*.00015,max(.001,min(price,close)-rng.random()*base*.00015),
                close,float(rng.randint(500,5000)),"SYNTHETIC",self.seconds))
            price=close
        return out

def export_csv(bars: Iterable[Bar],path: str|Path):
    with Path(path).open("w",encoding="utf-8",newline="") as f:
        writer=csv.writer(f)
        writer.writerow(("symbol","ts","open","high","low","close","volume","source","seconds"))
        for b in bars: writer.writerow((b.symbol,b.ts.isoformat(),b.open,b.high,b.low,b.close,b.volume,b.source,b.seconds))

def aggregate(bars: list[Bar],seconds: int) -> list[Bar]:
    """Return only complete UTC-aligned buckets. Missing base bars => omit bucket."""
    groups={}
    for b in bars:
        if seconds < b.seconds or seconds % b.seconds: raise ValueError("Timeframe must be a multiple of base")
        bucket=int(b.ts.timestamp())//seconds*seconds
        groups.setdefault((b.symbol,bucket,b.source,b.seconds),[]).append(b)
    out=[]
    for (symbol,t,source,base),rows in sorted(groups.items(),key=lambda x:x[0][1]):
        rows=sorted(rows,key=lambda b:b.ts)
        if len(rows)!=seconds//base or any(int(b.ts.timestamp())!=t+i*base for i,b in enumerate(rows)): continue
        out.append(Bar(symbol,datetime.fromtimestamp(t,UTC),rows[0].open,max(b.high for b in rows),
            min(b.low for b in rows),rows[-1].close,sum(b.volume for b in rows),source,seconds))
    return out

class CandleStore:
    def __init__(self,path):
        self.db=sqlite3.connect(path)
        self.db.execute("CREATE TABLE IF NOT EXISTS candles(symbol TEXT,ts TEXT,seconds INT,source TEXT,payload TEXT,PRIMARY KEY(symbol,ts,seconds,source))")

    def put(self,bars):
        from dataclasses import asdict
        with self.db:
            for b in bars:
                payload=asdict(b);payload["ts"]=b.ts.isoformat()
                args=(b.symbol,b.ts.isoformat(),b.seconds,b.source,json.dumps(payload,allow_nan=False))
                old=self.db.execute("SELECT payload FROM candles WHERE symbol=? AND ts=? AND seconds=? AND source=?",args[:4]).fetchone()
                if old and old[0]!=args[4]: raise ValueError("Historical candle revision requires explicit reimport")
                self.db.execute("INSERT OR IGNORE INTO candles VALUES(?,?,?,?,?)",args)

    def load(self,symbol,seconds=60,source="SYNTHETIC") -> list[Bar]:
        rows=self.db.execute("SELECT payload FROM candles WHERE symbol=? AND seconds=? AND source=? ORDER BY ts",(symbol,seconds,source)).fetchall()
        result=[]
        for row in rows:
            record=json.loads(row[0]);record["ts"]=datetime.fromisoformat(record["ts"])
            result.append(Bar(**record))
        return result

    def close(self): self.db.close()
