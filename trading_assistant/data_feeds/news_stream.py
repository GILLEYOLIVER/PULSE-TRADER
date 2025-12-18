from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from threading import Event
from typing import AsyncIterator, List, Optional, Set

from trading_assistant.config import NewsFeedConfig
from trading_assistant.core.models import NewsItem

from trading_assistant.data_feeds.news_sources.alpha_vantage import AlphaVantageNewsClient
from trading_assistant.data_feeds.news_sources.finnhub_client import FinnhubNewsClient
from trading_assistant.data_feeds.news_sources.gdelt_client import GDELTNewsClient


def _stable_id(item: NewsItem) -> str:
    base = f"{item.source}|{item.title}|{item.url}".encode("utf-8", errors="ignore")
    return hashlib.sha1(base).hexdigest()


@dataclass
class MultiSourceNewsConnector:
    config: NewsFeedConfig

    async def stream_news(self, stop_event: Optional[Event] = None) -> AsyncIterator[NewsItem]:
        import asyncio

        seen: Set[str] = set()

        # clients (só instanciar se tiver chave)
        av_client = None
        if self.config.sources.alphavantage_enabled and self.config.sources.alphavantage_api_key:
            av_client = AlphaVantageNewsClient(self.config.sources.alphavantage_api_key)

        fh_client = None
        if self.config.sources.finnhub_enabled and self.config.sources.finnhub_api_key:
            fh_client = FinnhubNewsClient(self.config.sources.finnhub_api_key)

        gd_client = None
        if self.config.sources.gdelt_enabled:
            gd_client = GDELTNewsClient()

        # fallback (sem chaves -> não trava o app)
        if self.config.mock_mode or (av_client is None and fh_client is None and gd_client is None):
            while True:
                if stop_event and stop_event.is_set():
                    return
                yield NewsItem(ts=datetime.utcnow(), title="(mock) Mercado em observação", source="Mock", sentiment=0.0, impact=0.1)
                await _sleep_interruptible(self.config.sources.poll_seconds, stop_event=stop_event)
            return

        while True:
            if stop_event and stop_event.is_set():
                return

            items: List[NewsItem] = []

            async def fetch_av():
                if not av_client:
                    return []
                # tickers: use CRYPTO:BTC/FOREX:USD etc se quiser depois. Agora busca por tópicos gerais.
                return await asyncio.to_thread(av_client.fetch, None, None, 80)

            async def fetch_fh():
                if not fh_client:
                    return []
                return await asyncio.to_thread(fh_client.general_news, "general", 60)

            async def fetch_gd():
                if not gd_client:
                    return []
                # busca por algumas keywords principais (limitado por polling)
                kws = list(self.config.keywords)[:6]
                out: List[NewsItem] = []
                for kw in kws:
                    out.extend(await asyncio.to_thread(gd_client.fetch, kw, 1, 12))
                return out

            results = await asyncio.gather(fetch_av(), fetch_fh(), fetch_gd(), return_exceptions=True)
            for res in results:
                if isinstance(res, Exception):
                    continue
                items.extend(res or [])

            # dedupe + yield
            for it in items:
                sid = _stable_id(it)
                if sid in seen:
                    continue
                seen.add(sid)
                # controla crescimento do set
                if len(seen) > 3000:
                    seen = set(list(seen)[-1500:])
                yield it

            await _sleep_interruptible(self.config.sources.poll_seconds, stop_event=stop_event)


async def _sleep_interruptible(seconds: int, stop_event: Optional[Event] = None) -> None:
    import asyncio
    total = max(1, int(seconds))
    step = 0.1
    slices = int(total / step)
    for _ in range(max(1, slices)):
        if stop_event and stop_event.is_set():
            return
        await asyncio.sleep(step)
