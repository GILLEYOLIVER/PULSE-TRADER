"""Dated financial/corporate context. Current snapshots never leak into a past replay."""
from __future__ import annotations

import csv
import io
import json
import os
import re
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

from .market_data import http_bytes, json_response, brapi_result
from .models import UTC, aware, finite
from .session import SAO_PAULO


def company_filings(raw, cnpj, as_of):
    cnpj = re.sub(r'\D', '', cnpj or '')
    if len(cnpj) != 14:
        return []
    result = []
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        for name in archive.namelist():
            if not name.lower().endswith('.csv'):
                continue
            if archive.getinfo(name).file_size > 80_000_000:
                raise ValueError('Arquivo de comunicados acima do limite')
            payload = archive.read(name)
            try:
                text = payload.decode('utf-8-sig')
            except UnicodeDecodeError:
                text = payload.decode('latin1')
            for row in csv.DictReader(io.StringIO(text), delimiter=';'):
                if re.sub(r'\D', '', row.get('CNPJ_Companhia', '')) != cnpj:
                    continue
                # The bulk dataset may have only a date: admit it after the entire publication day.
                day = datetime.fromisoformat(row['Data_Entrega'][:10]).replace(tzinfo=SAO_PAULO)
                available = aware(day + timedelta(days=1))
                if available > as_of:
                    continue
                category = row.get('Categoria', '')
                if category not in ('Fato Relevante', 'Comunicado ao Mercado', 'Aviso aos Acionistas', 'Dados Econômico-Financeiros'):
                    continue
                link = row.get('Link_Download', '')
                result.append({'available_at': available.isoformat(), 'category': category,
                               'headline': row.get('Assunto', '')[:1000],
                               'url': link if link.startswith('https://') else '', 'source': 'CVM_IPE'})
    return sorted(result, key=lambda item: item['available_at'], reverse=True)[:30]


def fetch_company_context(symbol, directory, *, now=None, getter=json_response, binary_getter=http_bytes):
    now = aware(now or datetime.now(UTC))
    symbol = symbol.strip().upper()
    if not re.fullmatch(r'[A-Z0-9]{2,16}', symbol):
        raise ValueError('Código de ativo inválido')
    if symbol in ('BTC', 'ETH', 'WIN', 'WDO', 'IND', 'DOL'):
        raise ValueError('Fundamentos de companhia se aplicam a ações, não a este instrumento')
    token = os.getenv('BRAPI_TOKEN') or None
    result = {'symbol': symbol, 'available_at': now.isoformat(), 'sources': ['BRAPI'], 'fundamentals': {},
              'dividends': [], 'filings': [], 'errors': [], 'historical_point_in_time': False}
    for endpoint, key in (('financial-data', 'fundamentals'), ('dividends', 'dividends'), ('profile', 'profile')):
        try:
            data = brapi_result(getter(f'https://brapi.dev/api/v2/stocks/{endpoint}?symbols={symbol}', token=token), symbol)
            if key == 'dividends':
                result[key] = data.get('cashDividends', []) + data.get('stockDividends', [])
            else:
                result[key] = data
        except ValueError as error:
            result['errors'].append(f'{endpoint}: {error}')
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    cnpj = result.get('profile', {}).get('cnpj')
    if cnpj:
        cache = directory / f'cvm-ipe-{now.year}.zip'
        try:
            if not cache.exists() or now.timestamp() - cache.stat().st_mtime > 86400:
                raw = binary_getter(f'https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/IPE/DADOS/ipe_cia_aberta_{now.year}.zip')
                # Validate before replacing a usable cache; archive files are read in memory, never extracted.
                company_filings(raw, cnpj, now)
                temporary = cache.with_suffix('.tmp')
                temporary.write_bytes(raw)
                temporary.replace(cache)
            result['filings'] = company_filings(cache.read_bytes(), cnpj, now)
            result['sources'].append('CVM_IPE')
        except (ValueError, OSError, zipfile.BadZipFile) as error:
            result['errors'].append(f'CVM: {error}')
    if not result['fundamentals'] and not result['dividends'] and not result['filings']:
        raise ValueError('Contexto indisponível nas fontes consultadas; não foi substituído por dados fictícios')
    path = directory / f'{symbol}.json'
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    temporary.replace(path)
    return result


def summarize_context(snapshot, *, as_of, side=None):
    as_of = aware(as_of)
    if aware(datetime.fromisoformat(snapshot['available_at'])) > as_of:
        return {'lines': ['Contexto atual excluído deste replay histórico para evitar dados futuros.'],
                'review_required': False, 'included': False}
    fundamentals = snapshot.get('fundamentals', {})
    lines, warnings = [], []
    margin, cash = fundamentals.get('profitMargins'), fundamentals.get('freeCashflow')
    debt, assets, ebitda = (fundamentals.get(key) for key in ('totalDebt', 'totalCash', 'ebitda'))
    if finite(margin):
        lines.append(f'Margem líquida de 12 meses: {margin:.1%}.')
        if margin < 0:
            warnings.append('Companhia com margem líquida negativa; revisar cenário comprador.')
    if finite(cash):
        lines.append(f'Fluxo de caixa livre: R$ {cash:,.0f}.')
        if cash < 0:
            warnings.append('Fluxo de caixa livre negativo.')
    if finite(debt, assets, ebitda) and ebitda > 0:
        leverage = (debt-assets)/ebitda
        lines.append(f'Dívida líquida/EBITDA calculada: {leverage:.2f}x.')
        if leverage > 3:
            warnings.append('Dívida líquida acima de 3x EBITDA; revisar exposição.')
    for event in snapshot.get('dividends', []):
        approved = event.get('approvedOn')
        if not approved or aware(datetime.fromisoformat(approved.replace('Z', '+00:00'))) > as_of:
            continue
        date = event.get('exDate')
        if date:
            ex = aware(datetime.fromisoformat(date.replace('Z', '+00:00')))
            if abs((ex-as_of).total_seconds()) <= 7*86400:
                warnings.append(f"Evento {event.get('label', 'provento')} com data ex {ex.date()}; o preço pode ajustar mecanicamente.")
    current_filings = [item for item in snapshot.get('filings', [])
                       if aware(datetime.fromisoformat(item['available_at'])) <= as_of]
    for item in current_filings[:3]:
        lines.append(f"{item['category']}: {item['headline']} ({item['available_at'][:10]}).")
    if any(item['category'] == 'Fato Relevante' and
           (as_of-datetime.fromisoformat(item['available_at'])).total_seconds() <= 7*86400 for item in current_filings):
        warnings.append('Fato relevante recente; leia o comunicado antes de armar uma entrada.')
    if (as_of-datetime.fromisoformat(snapshot['available_at'])).total_seconds() > 7*86400:
        warnings.append('Contexto financeiro consultado há mais de sete dias; atualizar.')
    if snapshot.get('errors'):
        warnings.append('Cobertura parcial: ' + '; '.join(snapshot['errors']))
    if not lines:
        lines.append('Sem indicadores financeiros utilizáveis neste snapshot; cobertura insuficiente.')
        warnings.append('Revisão manual de fundamentos necessária.')
    return {'lines': lines + warnings, 'review_required': bool(warnings), 'included': True,
            'available_at': snapshot['available_at'], 'sources': snapshot.get('sources', [])}
