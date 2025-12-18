from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional

import requests
from dateutil import parser as dtparser

from trading_assistant.core.models import NewsItem


@dataclass
class FinnhubNewsClient:
    api_key: str
    session: requests.Session = requests.Session()
    base_url: str = "https://finnhub.io/api/v1"

    def general_news(self, category: str = "general", limit: int = 50) -> List[NewsItem]:
        url = f"{self.base_url}/news"
        params = {"category": category, "token": self.api_key}
        r = self.session.get(url, params=params, timeout=25)
        r.raise_for_status()
        data = r.json() or []
        return self._to_items(data, source_default="Finnhub", limit=limit)

    def company_news(self, symbol: str, days_back: int = 3, limit: int = 50) -> List[NewsItem]:
        url = f"{self.base_url}/company-news"
        to_dt = datetime.utcnow().date()
        from_dt = (datetime.utcnow() - timedelta(days=days_back)).date()
        params = {"symbol": symbol, "from": str(from_dt), "to": str(to_dt), "token": self.api_key}
        r = self.session.get(url, params=params, timeout=25)
        r.raise_for_status()
        data = r.json() or []
        return self._to_items(data, source_default="Finnhub", limit=limit)

    def _to_items(self, data, source_default: str, limit: int) -> List[NewsItem]:
        out: List[NewsItem] = []
        for it in (data[: max(1, int(limit))]):
            title = str(it.get("headline") or it.get("title") or "").strip()
            if not title:
                continue
            url_ = str(it.get("url") or "").strip()
            source = str(it.get("source") or source_default).strip()
            lang = str(it.get("language") or "").strip()

            ts = datetime.utcnow()
            # Finnhub traz "datetime" em epoch seconds em muitos endpoints
            if "datetime" in it:
                try:
                    ts = datetime.utcfromtimestamp(int(it["datetime"]))
                except Exception:
                    pass
            elif "publishedAt" in it:
                try:
                    ts = dtparser.parse(str(it["publishedAt"]))
                except Exception:
                    pass

            # Finnhub não dá sentimento em todos endpoints → impacto neutro
            out.append(NewsItem(
                ts=ts,
                title=title,
                source=source,
                url=url_,
                language=lang,
                sentiment=0.0,
                impact=0.3,
            ))
        return out
