"""Bounded, resumable public histories for research; ordinary UI limits stay intact."""
from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime,timedelta
from pathlib import Path

from .data import CSVProvider
from .learning import digest
from .market_data import fetch_binance
from .models import UTC,aware
from .research import atomic_json
from .suggestions import history_digest,validate_series

MAX_RESEARCH_BARS=100000
MIN_FREE_BYTES=256*1024**2


def checked_json(path):
    value=json.loads(Path(path).read_text(encoding='utf-8'));claimed=value.pop('manifest_sha256',None)
    if digest(value)!=claimed:raise ValueError('Research history manifest checksum mismatch')
    return value,claimed


def save_checked(path,value):
    checksum=digest(value);atomic_json(path,{**value,'manifest_sha256':checksum});return checksum


def utc(value):
    parsed=datetime.fromisoformat(value) if isinstance(value,str) else value
    return aware(parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC))


def validate_part(bars,provenance,request):
    start,end=utc(request['start']),utc(request['end']);seconds=request['seconds']
    validate_series(bars)
    if any(b.symbol!=request['symbol'] or b.source!='BINANCE_SPOT_USDT' or b.seconds!=seconds
        or not start<=b.ts or b.ts+timedelta(seconds=seconds)>end
        or b.ts.timestamp()%seconds!=0 for b in bars):
        raise ValueError('Research chunk has incompatible or out-of-window candles')
    expected=int((end-start).total_seconds())//seconds
    if (provenance.get('sha256')!=history_digest(bars) or provenance.get('candles')!=len(bars)
        or provenance.get('expected_candles')!=expected
        or provenance.get('missing_candles')!=expected-len(bars)):
        raise ValueError('Research chunk coverage or data checksum mismatch')


def get_research_history(symbol,seconds,start,end,output,*,fetcher=None,chunk_bars=10000):
    """Every part is <=10,000 bars; <=5% missing across the complete interval."""
    if symbol not in ('BTCUSDT','ETHUSDT','BNBUSDT','SOLUSDT') or seconds not in (60,300,900,1800,3600,86400):
        raise ValueError('Unsupported public research market or timeframe')
    if type(seconds) is not int or type(chunk_bars) is not int or not 1<=chunk_bars<=10000:
        raise ValueError('Invalid research chunk size')
    start,end=utc(start),utc(end)
    if end>datetime.now(UTC):raise ValueError('Research history requires past closed-candle windows')
    step=seconds*1000
    first=(int(start.timestamp()*1000)+step-1)//step*step
    last=int(end.timestamp()*1000)//step*step
    expected=(last-first)//step
    if not 1<=expected<=MAX_RESEARCH_BARS:raise ValueError('Research history must contain 1 to 100,000 complete candles')
    start=datetime.fromtimestamp(first/1000,UTC);end=datetime.fromtimestamp(last/1000,UTC)
    request={'symbol':symbol,'seconds':seconds,'start':start.isoformat(),'end':end.isoformat(),'chunk_bars':chunk_bars}
    root=Path(output)/'data'/('research-'+digest(request)[:20]);root.mkdir(parents=True,exist_ok=True)
    complete=root/'manifest.json';previous=None
    if complete.exists():
        previous,_=checked_json(complete)
        if previous['request']!=request:raise ValueError('Research history cache belongs to another request')
    rows=[];parts=[];gaps=[];abbreviated=[];cursor=start;index=0
    while cursor<end:
        index+=1;until=min(end,cursor+timedelta(seconds=seconds*chunk_bars))
        part_request={**request,'start':cursor.isoformat(),'end':until.isoformat()}
        directory=root/f'part-{index:04d}';manifest=directory/'manifest.json'
        if manifest.exists():
            record,checksum=checked_json(manifest)
            if record['request']!=part_request:raise ValueError('Research chunk cache belongs to another interval')
            name=record['csv'];path=directory/name
            if Path(name).name!=name or not path.resolve().is_relative_to(directory.resolve()):
                raise ValueError('Research chunk path escapes its directory')
            if hashlib.sha256(path.read_bytes()).hexdigest()!=record['csv_sha256']:
                raise ValueError('Research chunk CSV checksum mismatch')
            bars=CSVProvider(path).bars();provenance=record['provenance']
        else:
            if previous is not None:raise ValueError('Completed research history is missing a preserved chunk')
            if shutil.disk_usage(root).free<MIN_FREE_BYTES+expected*512:
                raise ValueError('Insufficient free space; saved research chunks were preserved')
            market=(fetcher or fetch_binance)(symbol,seconds,start=cursor,end=until,allow_gaps=True)
            bars,provenance=market.bars,market.provenance
            validate_part(bars,provenance,part_request)
            path=market.save(directory)
            record={'request':part_request,'csv':path.name,'csv_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                'provenance':provenance}
            checksum=save_checked(manifest,record)
            print(f'Research chunk {index}: {symbol} {seconds}s {len(bars)} candles',flush=True)
        validate_part(bars,provenance,part_request)
        rows.extend(bars);gaps.extend(provenance.get('gaps',[]));abbreviated.extend(provenance.get('abbreviated_candles',[]))
        parts.append({'directory':directory.name,'manifest_sha256':checksum})
        cursor=until
    validate_series(rows)
    missing=expected-len(rows)
    record={'request':request,'expected_candles':expected,'candles':len(rows),'missing_candles':missing,
        'sha256':history_digest(rows),'parts':parts,'gaps':gaps,'abbreviated_candles':abbreviated,
        'gap_policy':'whole requested interval <=5%; preserve all original missing timestamps',
        'availability_clock':'nominal bucket end','mode':'READ_ONLY','live_quotes':False}
    if missing/expected>.05:
        save_checked(root/'rejection.json',{**record,'reason':'more_than_5_percent_missing'})
        raise ValueError('Mais de 5% do histórico completo sem candles; dados preservados, sem preenchimento')
    if previous is not None:
        if record!=previous:raise ValueError('Completed research history manifest no longer matches preserved data')
    else:save_checked(complete,record)
    return rows
