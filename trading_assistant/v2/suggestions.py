"""Technical scenarios from closed candles. No calibrated forecasts or order routing."""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta

from .indicators import snapshot
from .models import Bar, INSTRUMENTS, UTC, aware
from .strategy import Strategy


PROFILES = {"intraday": "No dia", "swing": "Dias e semanas"}
TRENDS = {"UP": "▲ ALTA", "DOWN": "▼ BAIXA", "FLAT": "● LATERAL", "UNKNOWN": "— SEM ANÁLISE"}
SETUPS = {"CONFIRMED": "Sinal técnico", "CONDITIONAL": "Aguardar gatilho", "WAIT": "Aguardar", "INSUFFICIENT": "Sem dados suficientes"}
STRATEGIES = {"trend": "Tendência", "breakout": "Rompimento", "pullback": "Retomada", "adaptive":"Regime, tendência e fluxo",
              "sma_cross":"Cruzamento SMA 20/50 e filtro 200", "ema_pullback":"Retomada EMA 9/21 e filtro 50"}


def history_digest(bars):
    digest = hashlib.sha256()
    for b in bars:
        row=[b.symbol, aware(b.ts).isoformat(), b.open, b.high, b.low,b.close,b.volume,b.source,b.seconds]
        if any(value is not None for value in b.activity()):row+=b.activity()
        digest.update(json.dumps(row,separators=(",", ":")).encode())
    return digest.hexdigest()


def matches_profile(seconds, profile):
    if profile not in PROFILES:
        raise ValueError("Perfil desconhecido")
    return 0 < seconds < 86400 if profile == "intraday" else seconds == 86400


def validate_series(bars):
    if not bars:
        raise ValueError("Série vazia")
    first = bars[0]
    if any((b.symbol, b.source, b.seconds) != (first.symbol, first.source, first.seconds) for b in bars):
        raise ValueError("Uma série deve ter um ativo, uma origem e um período")
    if any(b.ts < a.ts + timedelta(seconds=a.seconds) for a, b in zip(bars, bars[1:])):
        raise ValueError("Candles sobrepostos, duplicados ou fora de ordem")


def merge_series(existing, incoming):
    """Combine authorized files without revising saved candles or accepting overlap."""
    merged = {key: {bar.ts: bar for bar in bars} for key, bars in existing.items()}
    for bar in incoming:
        series = merged.setdefault((bar.symbol, bar.seconds, bar.source), {})
        if bar.ts in series and series[bar.ts] != bar:
            raise ValueError("Revisão de candle salvo exige uma nova importação explícita em outro catálogo")
        series[bar.ts] = bar
    result = {key: sorted(rows.values(), key=lambda bar: bar.ts) for key, rows in merged.items()}
    for bars in result.values():
        validate_series(bars)
    return result


@dataclass(frozen=True)
class Suggestion:
    symbol: str
    profile: str
    source: str
    seconds: int
    closed_at: datetime | None
    candles: int
    trend: str
    setup: str
    reason: str
    condition: str
    strategy: str | None = None
    side: str | None = None
    entry: float | None = None
    stop: float | None = None
    target: float | None = None
    data_sha256: str = ""
    history_sha256: str = ""

    def to_dict(self):
        record = asdict(self)
        record["closed_at"] = self.closed_at.isoformat() if self.closed_at else None
        record.update(mode="PAPER_ANALYSIS", confidence=None, probability_calibrated=False,
                      execution_enabled=False, analysis_type="technical_rules")
        return record


def analyze_series(bars, profile, *, as_of=None, parameters=None, instruments=None):
    """Analyze one ordered series, filtering incomplete/future candles before indicators."""
    bars = list(bars)
    validate_series(bars)
    first = bars[0]
    if not matches_profile(first.seconds, profile):
        raise ValueError("Use candles intradiários para No dia e diários (86400 s) para Dias e semanas")
    cutoff = aware(as_of or datetime.now(UTC))
    closed = [b for b in bars if aware(b.ts) + timedelta(seconds=b.seconds) <= cutoff]
    base = dict(symbol=first.symbol, profile=profile, source=first.source, seconds=first.seconds,
                closed_at=aware(closed[-1].ts) + timedelta(seconds=first.seconds) if closed else None,
                candles=len(closed), data_sha256=history_digest(closed), history_sha256=history_digest(closed[-1000:]))
    if len(closed) < 35:
        return Suggestion(**base, trend="UNKNOWN", setup="INSUFFICIENT",
                          reason=f"{len(closed)} candles encerrados; são necessários pelo menos 35.",
                          condition="Importe mais histórico ou avance o replay.")

    history = closed[-1000:]
    b = history[-1]
    ind = snapshot(history)
    spread = ind["ema_fast"] - ind["ema_slow"]
    if ind["atr"] > 0 and abs(spread) >= ind["atr"] * .15 and spread > 0 and ind["momentum"] > 0 and b.close > ind["ema_slow"]:
        trend = "UP"
        reason = "Média de 9 períodos acima da de 21, preço acima da média lenta e impulso positivo."
    elif ind["atr"] > 0 and abs(spread) >= ind["atr"] * .15 and spread < 0 and ind["momentum"] < 0 and b.close < ind["ema_slow"]:
        trend = "DOWN"
        reason = "Média de 9 períodos abaixo da de 21, preço abaixo da média lenta e impulso negativo."
    else:
        trend = "FLAT"
        reason = "Médias, preço e impulso ainda não confirmam uma direção consistente."
    reason += f" RSI {ind['rsi']:.1f}; volume {ind['relative_volume']:.2f}x a média; ATR {ind['atr']:.4f}."
    spec = (instruments if instruments is not None else INSTRUMENTS).get(b.symbol)
    if spec is None:
        return Suggestion(**base, trend=trend, setup="WAIT", reason=reason,
                          condition="Ativo sem especificação de preço/lote no simulador; plano indisponível.")
    if ind["atr"] <= 0 or ind["volatility_ratio"] > 2.5:
        return Suggestion(**base, trend=trend, setup="WAIT", reason=reason,
                          condition="Aguardar volatilidade compatível com as regras de entrada.")

    parameters = parameters or Strategy()
    # Fixed rule priority, not a claim that the chosen template has the best future return.
    choices = [Strategy(name, parameters.reward_r, parameters.stop_atr, parameters.multi_timeframe).evaluate(history)
               for name in ("breakout", "trend", "pullback")]
    decision = next((d for d in choices if d is not None and d.side != "WAIT"), None)
    if decision is not None:
        side, raw_entry, raw_stop, raw_target = decision.side, decision.price, decision.stop, decision.target
        setup, strategy = "CONFIRMED", decision.strategy
        condition = "Sinal no último candle encerrado; entrada de referência a partir do candle seguinte, após validar o risco."
    elif trend != "FLAT":
        side = "BUY" if trend == "UP" else "SELL"
        direction = 1 if side == "BUY" else -1
        raw_entry = max(b.close, ind["resistance"] + spec.tick) if side == "BUY" else min(b.close, ind["support"] - spec.tick)
        distance = max(ind["atr"] * parameters.stop_atr, b.close * .0001)
        raw_stop, raw_target = raw_entry - direction * distance, raw_entry + direction * distance * parameters.reward_r
        setup, strategy = "CONDITIONAL", "breakout"
        condition = "Aguardar candle encerrado acima da resistência indicada e confirmar volume." if side == "BUY" else "Aguardar candle encerrado abaixo do suporte indicado e confirmar volume."
    else:
        return Suggestion(**base, trend=trend, setup="WAIT", reason=reason,
                          condition="Sem entrada, stop ou alvo enquanto não houver um cenário direcional.")

    # Conservative rounding: entry/stop adverse; target rounded toward entry.
    rounding = (math.ceil, math.floor, math.floor) if side == "BUY" else (math.floor, math.ceil, math.ceil)
    entry, stop, target = [round(fn(value / spec.tick) * spec.tick, 10)
                           for fn, value in zip(rounding, (raw_entry, raw_stop, raw_target))]
    valid = 0 < stop < entry < target if side == "BUY" else 0 < target < entry < stop
    if not valid:
        return Suggestion(**base, trend=trend, setup="WAIT", reason=reason,
                          condition="Níveis incompatíveis com o preço e o tick deste ativo; aguardar.")
    return Suggestion(**base, trend=trend, setup=setup, reason=reason, condition=condition,
                      strategy=strategy, side=side, entry=entry, stop=stop, target=target)


def save_plan(ledger, suggestion, *, saved_at, limits, costs, parameters, context=None, context_ack=False, instruments=None):
    """Save an analysis proposal only. Entry orders always remain in PaperEngine.submit."""
    if suggestion.entry is None:
        raise ValueError("Este cenário ainda não tem um plano de entrada")
    limits.validate()
    costs.validate()
    spec=(instruments if instruments is not None else INSTRUMENTS).get(suggestion.symbol)
    record = {"analysis": suggestion.to_dict(), "limits": asdict(limits), "execution": asdict(costs),
              "instrument":asdict(spec) if spec else None,
              "parameters": asdict(parameters), "state": "PROPOSAL_ONLY",
              "context": context, "context_ack": bool(context_ack),
              "risk_budget": limits.capital * limits.risk_fraction,
              "risk_approved": False, "quantity": None}
    key = hashlib.sha256(json.dumps(record, sort_keys=True, allow_nan=False).encode()).hexdigest()
    with ledger.transaction() as state:
        plans = state.setdefault("analysis_plans", {})
        if key not in plans:
            plans[key] = {**record, "saved_at": aware(saved_at).isoformat(), "id": key}
            ledger.audit(saved_at, "analysis_plan_saved", {"id": key, "symbol": suggestion.symbol, "profile": suggestion.profile})
        result = dict(plans[key])
    return result
