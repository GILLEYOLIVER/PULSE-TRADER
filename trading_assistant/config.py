from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional


def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    v = os.getenv(name)
    return v if v not in (None, "") else default


@dataclass
class MarketFeedConfig:
    # Lista padrão — você escolhe na UI também
    symbols: List[str] = field(default_factory=lambda: ["WIN", "WDO", "DOL", "IND", "BTC", "ETH"])
    timeframe_seconds: int = 5
    mock_mode: bool = True


@dataclass
class NewsSourcesConfig:
    enabled: bool = True
    poll_seconds: int = 20

    # Alpha Vantage NEWS_SENTIMENT
    alphavantage_enabled: bool = True
    alphavantage_api_key: Optional[str] = field(default_factory=lambda: _env("ALPHAVANTAGE_API_KEY"))

    # Finnhub news / company_news / general_news
    finnhub_enabled: bool = True
    finnhub_api_key: Optional[str] = field(default_factory=lambda: _env("FINNHUB_API_KEY"))

    # GDELT (sem chave)
    gdelt_enabled: bool = True
    gdelt_timespan: str = "1d"  # 1d, 7d, 1m, 3m, 1y (dependendo do endpoint / client)


@dataclass
class NewsFeedConfig:
    mock_mode: bool = False
    keywords: List[str] = field(default_factory=lambda: [
        "Fed", "FOMC", "Powell", "CPI", "PCE", "Payroll", "NFP", "Unemployment",
        "ECB", "BoE", "BOJ", "Copom", "Selic", "IPCA", "PIB", "GDP",
        "Oil", "OPEC", "Geopolitical", "War", "Sanctions",
        "Crypto", "Bitcoin", "Ethereum", "ETF", "SEC",
        "Tariff", "Trade war", "China", "USA", "Brazil"
    ])

    # Mapeamento de palavras-chave -> ativos afetados (ajuste com o tempo)
    # Ex.: notícia sobre juros EUA tende a impactar DOL/WDO/IND/WIN e BTC
    keyword_to_symbols: Dict[str, List[str]] = field(default_factory=lambda: {
        "Fed": ["DOL", "WDO", "IND", "WIN", "BTC", "ETH"],
        "FOMC": ["DOL", "WDO", "IND", "WIN", "BTC", "ETH"],
        "Powell": ["DOL", "WDO", "IND", "WIN", "BTC", "ETH"],
        "CPI": ["DOL", "WDO", "IND", "WIN", "BTC", "ETH"],
        "Payroll": ["DOL", "WDO", "IND", "WIN", "BTC", "ETH"],
        "NFP": ["DOL", "WDO", "IND", "WIN", "BTC", "ETH"],
        "Copom": ["DOL", "WDO", "IND", "WIN"],
        "Selic": ["DOL", "WDO", "IND", "WIN"],
        "IPCA": ["DOL", "WDO", "IND", "WIN"],
        "SEC": ["BTC", "ETH"],
        "ETF": ["BTC", "ETH"],
        "OPEC": ["DOL", "WDO", "IND", "WIN"],
        "Oil": ["DOL", "WDO", "IND", "WIN"],
    })

    sources: NewsSourcesConfig = field(default_factory=NewsSourcesConfig)


@dataclass
class SignalEngineConfig:
    # força do sinal (quanto maior, mais difícil gerar BUY/SELL)
    threshold: float = 2.5
    ema_fast: int = 9
    ema_slow: int = 21
    atr_period: int = 14
    # Gestão de trade (stops curtos + alvos longos)
    # stop_dist = stop_atr_mult * ATR
    # target_dist = stop_dist * reward_r
    stop_atr_mult: float = 0.70
    reward_r: float = 3.00

    # Filtragem adicional (evitar sinais fracos)
    min_confidence: float = 0.55

    # Cooldown (evita sinal a cada vela no mesmo ativo)
    cooldown_bars: int = 2


@dataclass
class RiskConfig:
    capital: float = 10000.0
    risk_per_trade: float = 0.005  # 0.5%
    max_daily_loss: float = 0.02   # 2% do capital
    max_trades_per_day: int = 8


@dataclass
class ValidatorConfig:
    max_spread: float = 0.30
    # trava quando impacto de notícia está muito alto
    max_news_impact: float = 3.5


@dataclass
class ExecutionConfig:
    mode: str = "paper"  # paper | live (live só no final, quando plugar Profit)
    slippage_bps: float = 2.0  # 2 bps (0.02%)


@dataclass
class NotifierConfig:
    enabled: bool = True
    console: bool = True


@dataclass
class AuditConfig:
    enabled: bool = True
    path: str = "audit.log"


@dataclass
class TradingAssistantConfig:
    market_feed: MarketFeedConfig = field(default_factory=MarketFeedConfig)
    news_feed: NewsFeedConfig = field(default_factory=NewsFeedConfig)
    signal_engine: SignalEngineConfig = field(default_factory=SignalEngineConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    validator: ValidatorConfig = field(default_factory=ValidatorConfig)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    notifier: NotifierConfig = field(default_factory=NotifierConfig)
    audit: AuditConfig = field(default_factory=AuditConfig)
