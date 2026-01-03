from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

import requests
from dateutil import parser as dtparser

from trading_assistant.core.models import NewsItem


@dataclass
class AlphaVantageNewsClient:
    api_key: str
    session: requests.Session = requests.Session()

    def fetch(self, tickers: Optional[List[str]] = None, topics: Optional[List[str]] = None, limit: int = 50) -> List[NewsItem]:
        # Docs: function=NEWS_SENTIMENT, tickers, topics, time_from, limit... (Alpha Vantage)
        url = "https://www.alphavantage.co/query"
        params = {
            "function": "NEWS_SENTIMENT",
            "apikey": self.api_key,
            "limit": min(1000, max(1, int(limit))),
        }
        if tickers:
            params["tickers"] = ",".join(tickers)
        if topics:
            params["topics"] = ",".join(topics)

        r = self.session.get(url, params=params, timeout=25)
        r.raise_for_status()
        data = r.json()

        feed = data.get("feed", []) or []
        out: List[NewsItem] = []
        for it in feed:
            title = str(it.get("title", "")).strip()
            if not title:
                continue
            source = str(it.get("source", "AlphaVantage")).strip()
            url_ = str(it.get("url", "")).strip()

            # Alpha Vantage usa time_published (YYYYMMDDTHHMMSS)
            ts_raw = it.get("time_published") or it.get("published_utc") or ""
            ts = datetime.utcnow()
            try:
                ts = dtparser.parse(str(ts_raw))
            except Exception:
                pass

            # sentiment geral
            sent = 0.0
            try:
                sent = float(it.get("overall_sentiment_score", 0.0))
            except Exception:
                sent = 0.0

            # impacto aproximado: usa relevância média das "ticker_sentiment" se existir
            impact = 0.0
            tss = it.get("ticker_sentiment") or []
            rels = []
            for t in tss:
                try:
                    rels.append(float(t.get("relevance_score", 0.0)))
                except Exception:
                    pass
            if rels:
                impact = float(sum(rels) / max(1, len(rels)))
            else:
                impact = min(1.0, abs(sent))

            tickers_out = []
            for t in tss:
                sym = str(t.get("ticker", "")).strip()
                if sym:
                    tickers_out.append(sym)

            topics_out = []
            for t in (it.get("topics") or []):
                name = str(t.get("topic", "")).strip()
                if name:
                    topics_out.append(name)

            out.append(NewsItem(
                ts=ts,
                title=title,
                source=source,
                url=url_,
                sentiment=max(-1.0, min(1.0, sent)),
                impact=max(0.0, min(1.0, impact)),
                tickers=tickers_out,
                topics=topics_out,
            ))
        return out
