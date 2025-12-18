from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List

from dateutil import parser as dtparser

from trading_assistant.core.models import NewsItem

try:
    from gdeltdoc import GdeltDoc, Filters
except Exception:  # pragma: no cover
    GdeltDoc = None
    Filters = None


@dataclass
class GDELTNewsClient:
    def fetch(self, keyword: str, timespan_days: int = 1, limit: int = 50) -> List[NewsItem]:
        if GdeltDoc is None or Filters is None:
            return []

        gd = GdeltDoc()
        end = datetime.utcnow().date()
        start = (datetime.utcnow() - timedelta(days=max(1, int(timespan_days)))).date()

        f = Filters(
            keyword=keyword,
            start_date=str(start),
            end_date=str(end),
        )

        try:
            arts = gd.article_search(f)  # pandas dataframe
        except Exception:
            return []

        out: List[NewsItem] = []
        # expected columns: title, url, sourceCountry, language, seendate, ...
        try:
            rows = arts.to_dict(orient="records")
        except Exception:
            rows = []

        for it in rows[: max(1, int(limit))]:
            title = str(it.get("title", "")).strip()
            if not title:
                continue
            url_ = str(it.get("url", "")).strip()
            source = str(it.get("sourceCountry", "GDELT")).strip()
            lang = str(it.get("language", "")).strip()
            ts = datetime.utcnow()
            try:
                ts = dtparser.parse(str(it.get("seendate", "")))
            except Exception:
                pass

            # GDELT aqui: sem sentimento nativo → neutro, impacto baixo/moderado
            out.append(NewsItem(
                ts=ts,
                title=title,
                source=f"GDELT/{source}",
                url=url_,
                language=lang,
                sentiment=0.0,
                impact=0.25,
            ))
        return out
