"""Read-only public market data. This module has no broker/account/order endpoints."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from .data import CSVProvider, export_csv
from .models import Bar, UTC, aware
from .session import SAO_PAULO
from .suggestions import merge_series, history_digest


class DataUnavailable(ValueError):
    pass


def http_bytes(url, *, token=None, limit=32_000_000):
    headers = {'User-Agent': 'PULSE-TRADER/2.1 read-only analysis', 'Accept': 'application/json,text/csv,application/zip'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=20) as response:
            raw = response.read(limit + 1)
    except urllib.error.HTTPError as error:
        raise DataUnavailable(f'Provedor respondeu HTTP {error.code}; confira disponibilidade, plano e permissões da fonte.') from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise DataUnavailable('Não foi possível consultar a fonte de dados. Tente novamente; os dados salvos foram preservados.') from None
    if len(raw) > limit:
        raise DataUnavailable('Resposta do provedor acima do limite permitido')
    return raw


def json_response(url, *, token=None):
    try:
        return json.loads(http_bytes(url, token=token))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise DataUnavailable('O provedor não retornou um JSON válido') from None


def brapi_result(payload, symbol):
    for item in payload.get('results', []):
        if item.get('requestedSymbol', item.get('symbol')) == symbol:
            if item.get('symbol') != symbol or item.get('changed'):
                raise DataUnavailable('Ticker alterado pelo provedor; confira a identificação antes de importar')
            if not isinstance(item.get('data'), dict):
                raise DataUnavailable('Dados indisponíveis para este ativo no provedor')
            return item['data']
    raise DataUnavailable('Ativo ausente na resposta do provedor')


@dataclass
class MarketSnapshot:
    bars: list[Bar]
    provenance: dict

    def save(self, directory):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        name = f"{self.bars[0].symbol}-{self.bars[0].seconds}-{self.provenance['sha256'][:12]}"
        path = directory / (name + '.csv')
        export_csv(self.bars, path)
        path.with_suffix('.json').write_text(json.dumps(self.provenance, indent=2), encoding='utf-8')
        return path


def fetch_market(symbol, seconds=86400, *, provider='brapi', window='2y', now=None, getter=json_response):
    symbol = symbol.upper().strip()
    if not re.fullmatch(r'[A-Z0-9]{2,16}', symbol):
        raise ValueError('Código de ativo inválido')
    now = aware(now or datetime.now(UTC))
    if provider=='binance':
        days={'5d':5,'1mo':30,'3mo':90,'1y':365,'2y':730,'5y':1825}
        if window not in days:raise ValueError('Binance: use um intervalo de 5d a 5y')
        return fetch_binance(symbol,seconds,start=now-timedelta(days=days[window]),end=now,getter=getter)
    if provider == 'brapi':
        intervals = {60: '1m', 300: '5m', 900: '15m', 1800: '30m', 3600: '60m', 86400: '1d'}
        if seconds not in intervals or window not in ('5d', '1mo', '3mo', '1y', '2y', '5y', 'max'):
            raise ValueError('Período não suportado pela brapi')
        token = os.getenv('BRAPI_TOKEN') or None
        if not token and symbol not in ('PETR4', 'VALE3', 'ITUB4', 'MGLU3'):
            raise DataUnavailable('Sem token, use PETR4, VALE3, ITUB4 ou MGLU3. Outros ativos dependem do plano brapi; WIN/WDO podem ser importados do Profit.')
        query = urllib.parse.urlencode(dict(symbols=symbol, range=window, interval=intervals[seconds], sortOrder='asc'))
        payload = getter('https://brapi.dev/api/v2/stocks/historical?' + query, token=token)
        data = brapi_result(payload, symbol)
        if data.get('usedInterval') != intervals[seconds]:
            raise DataUnavailable('O provedor retornou um período diferente do solicitado')
        bars = [Bar(symbol, datetime.fromtimestamp(row['date'], UTC),
                    *(float(row[key]) for key in ('open', 'high', 'low', 'close', 'volume')),
                    'BRAPI_RAW', seconds) for row in data.get('historicalDataPrice', [])]
        basis = 'OHLC original; adjustedClose não substitui isoladamente o fechamento. Proventos não estão no retorno de preço.'
        documentation = 'https://brapi.dev/docs/acoes/historico'
    elif provider == 'mercado_bitcoin':
        resolutions = {60: '1m', 900: '15m', 3600: '1h', 10800: '3h', 86400: '1d'}
        if symbol not in ('BTC', 'ETH') or seconds not in resolutions:
            raise ValueError('Mercado Bitcoin: use BTC ou ETH em BRL e período 1 min, 15 min, 1h, 3h ou diário')
        query = urllib.parse.urlencode(dict(symbol=symbol + '-BRL', resolution=resolutions[seconds], to=int(now.timestamp()), countback=1000))
        payload = getter('https://api.mercadobitcoin.net/api/v4/candles?' + query)
        keys = ('t', 'o', 'h', 'l', 'c', 'v')
        if any(key not in payload for key in keys) or len({len(payload[key]) for key in keys}) != 1:
            raise DataUnavailable('Candles incompletos na resposta do Mercado Bitcoin')
        bars = [Bar(symbol, datetime.fromtimestamp(int(t), UTC), float(o), float(h), float(l), float(c), float(v),
                    'MERCADO_BITCOIN_BRL', seconds) for t, o, h, l, c, v in zip(*(payload[key] for key in keys))]
        basis, documentation = 'Mercado spot em BRL; sem derivativos ou conversão de dólar.', 'https://api.mercadobitcoin.net/api/v4/docs'
    else:
        raise ValueError('Provedor desconhecido')
    bars = sorted((bar for bar in bars if aware(bar.ts) + timedelta(seconds=bar.seconds) <= now), key=lambda bar: bar.ts)
    if not bars:
        raise DataUnavailable('Nenhum candle encerrado foi retornado')
    merge_series({}, bars)
    response_digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    digest = history_digest(bars)
    return MarketSnapshot(bars, {'provider': provider, 'symbol': symbol, 'seconds': seconds, 'retrieved_at': now.isoformat(),
                                'last_closed_at': (bars[-1].ts + timedelta(seconds=seconds)).isoformat(),
                                'candles': len(bars), 'sha256': digest, 'response_sha256':response_digest, 'price_basis': basis, 'documentation': documentation,
                                'mode': 'READ_ONLY', 'live_quotes': False})


def fetch_binance(symbol,seconds,*,start,end,getter=json_response):
    """Public spot-only OHLC + closed-candle activity; no account/order URLs."""
    intervals={60:'1m',300:'5m',900:'15m',1800:'30m',3600:'1h',86400:'1d'}
    if symbol not in ('BTCUSDT','ETHUSDT') or seconds not in intervals:
        raise ValueError('Binance: BTCUSDT/ETHUSDT, 1m/5m/15m/30m/1h/diário; valores em USDT')
    start,end=aware(start),aware(end)
    step=seconds*1000
    cursor=((int(start.timestamp()*1000)+step-1)//step)*step
    until=int(end.timestamp()*1000)//step*step
    if not cursor<until or (until-cursor)//step>10000:
        raise ValueError('Escolha um intervalo com 1 a 10.000 candles completos por consulta')
    bars=[];pages=[]
    while cursor<until:
        query=urllib.parse.urlencode(dict(symbol=symbol,interval=intervals[seconds],startTime=cursor,endTime=until-1,limit=1000))
        payload=getter('https://data-api.binance.vision/api/v3/klines?'+query)
        if not isinstance(payload,list) or not payload:raise DataUnavailable('Histórico Binance incompleto no intervalo solicitado')
        pages.append(hashlib.sha256(json.dumps(payload,separators=(',',':')).encode()).hexdigest())
        previous=cursor-step
        for row in payload:
            if (not isinstance(row,list) or len(row)<11 or type(row[0]) is not int or type(row[6]) is not int
                or row[0]!=previous+step or row[6]!=row[0]+step-1 or row[0]>=until or type(row[8]) is not int):
                raise DataUnavailable('Candle Binance ausente, fora de ordem ou com horário incompatível')
            bars.append(Bar(symbol,datetime.fromtimestamp(row[0]/1000,UTC),
                *(float(row[index]) for index in (1,2,3,4,5)),'BINANCE_SPOT_USDT',seconds,
                float(row[7]),int(row[8]),float(row[9])))
            previous=row[0]
        cursor=previous+step
    return MarketSnapshot(bars,{'provider':'binance','symbol':symbol,'currency':'USDT','seconds':seconds,
        'retrieved_at':datetime.now(UTC).isoformat(),'last_closed_at':(bars[-1].ts+timedelta(seconds=seconds)).isoformat(),
        'candles':len(bars),'sha256':history_digest(bars),'page_sha256':pages,
        'price_basis':'Spot USDT; volume base, volume financeiro, negócios e compras agressoras reais do candle encerrado',
        'documentation':'https://github.com/binance/binance-spot-api-docs/blob/master/faqs/market_data_only.md',
        'mode':'READ_ONLY','live_quotes':False})


def normalized_header(value):
    return re.sub(r'[^a-z0-9]', '', unicodedata.normalize('NFKD', value.strip().lower()).encode('ascii', 'ignore').decode())


def decimal_pt(value):
    value = value.strip().replace('R$', '').replace(' ', '')
    if ',' in value:
        value = value.replace('.', '').replace(',', '.')
    elif re.fullmatch(r'[+-]?\d{1,3}(?:\.\d{3})+',value):
        value=value.replace('.','')
    return float(value)


def read_profit_csv(path, *, seconds=60, symbol=None, timestamp_kind='open', source='PROFIT_USER_EXPORT'):
    """Explicit locale/clock conversion. Never interpret financial volume as units."""
    if timestamp_kind not in ('open', 'close') or type(seconds) is not int or seconds <= 0:
        raise ValueError('Informe período e se o horário exportado é abertura ou encerramento')
    raw = Path(path).read_bytes()
    try:
        text = raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        text = raw.decode('cp1252')
    delimiter = csv.Sniffer().sniff(text[:8192], delimiters=';,\t').delimiter
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    if {'symbol', 'ts', 'open', 'high', 'low', 'close', 'volume', 'source'} <= set(reader.fieldnames or []):
        return CSVProvider(path).bars()
    aliases = {'symbol': ('ativo', 'ticker', 'codigo'), 'date': ('data', 'datahora', 'datetime'), 'time': ('hora', 'horario'),
               'open': ('abertura', 'open'), 'high': ('maxima', 'high'), 'low': ('minima', 'low'),
               'close': ('fechamento', 'close', 'ultimo'),
               'volume': ('volumequantidade', 'quantidade', 'volumeqtd', 'qtdvolume')}
    header = {normalized_header(key): key for key in (reader.fieldnames or [])}
    columns = {key: next((header[name] for name in names if name in header), None) for key, names in aliases.items()}
    if any(columns[key] is None for key in ('date', 'open', 'high', 'low', 'close', 'volume')):
        raise ValueError('CSV do Profit precisa de data, OHLC e Volume Quantidade. Volume Financeiro não serve para dimensionar liquidez.')
    if not columns['symbol'] and not symbol:
        raise ValueError('Informe o ativo: este arquivo não tem coluna Ativo')
    bars = []
    for row in reader:
        clock = row[columns['date']].strip()
        if columns['time']:
            clock += ' ' + row[columns['time']].strip()
        timestamp = None
        for fmt in ('%d/%m/%Y %H:%M:%S', '%d/%m/%Y %H:%M', '%d/%m/%Y', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d'):
            try:
                timestamp = datetime.strptime(clock, fmt).replace(tzinfo=SAO_PAULO)
                break
            except ValueError:
                pass
        if timestamp is None:
            raise ValueError('Data/hora inválida no CSV do Profit')
        if timestamp_kind == 'close':
            timestamp -= timedelta(seconds=seconds)
        ticker = row[columns['symbol']].strip().upper() if columns['symbol'] else symbol.upper()
        bars.append(Bar(ticker, aware(timestamp), *(decimal_pt(row[columns[key]]) for key in ('open', 'high', 'low', 'close', 'volume')),
                        source, seconds))
    grouped = merge_series({}, bars)
    return sorted((bar for series in grouped.values() for bar in series), key=lambda bar: (bar.ts, bar.symbol))
