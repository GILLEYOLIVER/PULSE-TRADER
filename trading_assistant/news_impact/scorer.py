from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List

from trading_assistant.config import NewsFeedConfig
from trading_assistant.core.models import NewsItem


def _decay_minutes(age_minutes: float, half_life_minutes: float = 30.0) -> float:
    # decaimento exponencial: 0.5 a cada meia-vida
    if age_minutes <= 0:
        return 1.0
    return float(0.5 ** (age_minutes / max(1e-9, half_life_minutes)))


@dataclass
class NewsImpactScorer:
    cfg: NewsFeedConfig

    def score_items(self, items: List[NewsItem]) -> Dict[str, float]:
        # retorna score acumulado por símbolo (WIN/WDO/DOL/IND/BTC/ETH…)
        now = datetime.now(timezone.utc)
        scores: Dict[str, float] = {}

        for it in items:
            # idade
            ts = it.ts
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            age_min = (now - ts).total_seconds() / 60.0
            decay = _decay_minutes(age_min, half_life_minutes=45.0)

            title = (it.title or "").lower()
            sent = float(it.sentiment)
            imp = float(it.impact)

            # relevância: conta hits de keywords no título
            rel = 0.0
            hits = 0
            for kw in self.cfg.keywords:
                if kw.lower() in title:
                    hits += 1
            if hits > 0:
                rel = min(1.0, 0.25 + 0.15 * hits)

            # símbolos sugeridos
            symbols = set(it.symbols_hint or [])
            # inferência por keywords
            for kw, syms in self.cfg.keyword_to_symbols.items():
                if kw.lower() in title:
                    for s in syms:
                        symbols.add(s)

            if not symbols:
                continue

            # score do artigo: impacto * relevância * (sentimento em módulo para "força") * decaimento
            force = max(0.1, min(1.0, abs(sent) + 0.35))
            article_score = (imp * (0.4 + rel) * force) * decay

            for s in symbols:
                scores[s] = scores.get(s, 0.0) + float(article_score)

        return scores
