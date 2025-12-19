from __future__ import annotations
import os
from dataclasses import dataclass

@dataclass(frozen=True)
class Settings:
    # Modos: SIM (feed simulado), PAPER (ao vivo sem enviar ordem), REAL (envia ordem)
    MODE: str = os.getenv("PULSE_MODE", "PAPER").upper()

    # Postgres (opcional)
    PG_DSN: str | None = os.getenv("PULSE_PG_DSN")

    # Ativos (ex.: WINFUT, WDOFUT, DOL, BTCUSD)
    SYMBOLS: tuple[str, ...] = tuple(s.strip() for s in os.getenv("PULSE_SYMBOLS", "WIN").split(",") if s.strip())

    # Engine
    TICK_AGG_SECONDS: int = int(os.getenv("PULSE_TICK_AGG_SECONDS", "1"))

    # Risco
    CAPITAL: float = float(os.getenv("PULSE_CAPITAL", "10000"))
    RISK_PER_TRADE_PCT: float = float(os.getenv("PULSE_RISK_PER_TRADE_PCT", "0.5"))  # % do capital por trade
    MAX_DAILY_LOSS_PCT: float = float(os.getenv("PULSE_MAX_DAILY_LOSS_PCT", "2.0"))  # trava se perder isso no dia
    MAX_CONTRACTS: int = int(os.getenv("PULSE_MAX_CONTRACTS", "5"))

    # Regras de pausa (anti-tilt)
    MAX_STOPS_IN_ROW: int = int(os.getenv("PULSE_MAX_STOPS_IN_ROW", "3"))
    COOLDOWN_MINUTES: int = int(os.getenv("PULSE_COOLDOWN_MINUTES", "30"))

    # Slippage / custos (paper)
    SLIPPAGE_TICKS: int = int(os.getenv("PULSE_SLIPPAGE_TICKS", "1"))
    TICK_VALUE: float = float(os.getenv("PULSE_TICK_VALUE", "1.0"))   # valor por ponto/tick do ativo (ajuste por símbolo)
    TICK_SIZE: float = float(os.getenv("PULSE_TICK_SIZE", "1.0"))     # tamanho mínimo de variação

    # Notícias
    NEWS_ENABLED: bool = os.getenv("PULSE_NEWS_ENABLED", "1") == "1"
