"""Cached display series; never changes the engine's input candles or risk state."""
from functools import lru_cache
from statistics import mean

from .data import aggregate

CHART_PERIODS = (1, 5, 10, 15, 30, 60, 300, 900)


def period_label(seconds):
    return 'Diário' if seconds == 86400 else f'{seconds//60} min' if seconds % 60 == 0 else f'{seconds} s'


def available_periods(base):
    values = [seconds for seconds in CHART_PERIODS if seconds >= base and seconds % base == 0]
    if base not in values:
        values.insert(0, base)
    return {period_label(seconds): seconds for seconds in values}


def ema_series(values, period):
    result = [None] * len(values)
    if len(values) < period:
        return result
    average = mean(values[:period]);result[period-1] = average
    multiplier = 2/(period+1)
    for index in range(period, len(values)):
        average += multiplier*(values[index]-average)
        result[index] = average
    return result


@lru_cache(maxsize=4)
def chart_series(bars, seconds):
    """Immutable complete buckets and EMAs, reused while only the viewport moves."""
    rows = tuple(aggregate(bars, seconds))
    closes = [bar.close for bar in rows]
    return rows, tuple(ema_series(closes, 9)), tuple(ema_series(closes, 21))
