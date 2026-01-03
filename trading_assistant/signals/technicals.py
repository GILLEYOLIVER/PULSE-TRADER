from __future__ import annotations

"""Indicadores técnicos (simples e robustos).

Este projeto usa `atr()` em dois formatos possíveis:

1) atr(candles, period)
   - `candles` é uma lista de objetos com atributos: high, low, close

2) atr(highs, lows, closes, period)
   - listas numéricas

Para evitar que o app "pare" depois de alguns segundos (TypeError),
mantemos compatibilidade com os dois formatos.
"""

from typing import List, Optional, Sequence, Any


def ema(values: List[float], period: int) -> Optional[float]:
    if len(values) < period or period <= 0:
        return None
    k = 2 / (period + 1)
    e = float(values[0])
    for v in values[1:]:
        e = float(v) * k + e * (1 - k)
    return float(e)


def atr(
    a: Sequence[Any],
    b: Optional[Sequence[float]] = None,
    c: Optional[Sequence[float]] = None,
    period: int = 14,
) -> Optional[float]:
    """Average True Range (ATR).

    Suporta:
      - atr(candles, period)
      - atr(highs, lows, closes, period)
    """

    # Aceita chamada "atr(candles, period)" (2 args)
    # -> nesse caso o segundo argumento chega em `b`.
    if isinstance(b, (int, float)) and c is None:
        period = int(b)
        b = None

    # -----------------------------
    # Modo 1: atr(candles, period)
    # -----------------------------
    if b is None and c is None:
        candles = a
        if period <= 0:
            return None
        if len(candles) < period + 1:
            return None

        trs: List[float] = []
        # i começa em 1 porque TR usa close anterior
        for i in range(1, len(candles)):
            hi = float(getattr(candles[i], "high"))
            lo = float(getattr(candles[i], "low"))
            prev_close = float(getattr(candles[i - 1], "close"))
            tr = max(hi - lo, abs(hi - prev_close), abs(lo - prev_close))
            trs.append(float(tr))

        if len(trs) < period:
            return None
        return float(sum(trs[-period:]) / float(period))

    # ----------------------------------------------
    # Modo 2: atr(highs, lows, closes, period)
    # ----------------------------------------------
    highs = a
    lows = b
    closes = c
    if lows is None or closes is None:
        return None
    if period <= 0:
        return None
    if len(highs) < period + 1 or len(lows) < period + 1 or len(closes) < period + 1:
        return None

    trs2: List[float] = []
    for i in range(1, len(closes)):
        hi = float(highs[i])
        lo = float(lows[i])
        prev_close = float(closes[i - 1])
        tr = max(hi - lo, abs(hi - prev_close), abs(lo - prev_close))
        trs2.append(float(tr))

    if len(trs2) < period:
        return None
    return float(sum(trs2[-period:]) / float(period))
