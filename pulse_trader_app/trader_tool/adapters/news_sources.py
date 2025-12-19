from __future__ import annotations
import asyncio
from datetime import datetime, timezone
from typing import AsyncIterator
import feedparser
import aiohttp
from trader_tool.domain.models import NewsEvent

class RSSCollector:
    def __init__(self, feeds: list[str], poll_seconds: int = 60):
        self.feeds = feeds
        self.poll_seconds = poll_seconds
        self._seen: set[str] = set()

    async def stream(self) -> AsyncIterator[NewsEvent]:
        while True:
            for url in self.feeds:
                try:
                    d = feedparser.parse(url)
                    for e in d.entries[:20]:
                        key = getattr(e, "id", None) or getattr(e, "link", None) or getattr(e, "title", "")
                        if not key or key in self._seen:
                            continue
                        self._seen.add(key)
                        yield NewsEvent(
                            ts=datetime.now(timezone.utc),
                            source="RSS",
                            title=getattr(e, "title", "Sem título"),
                            url=getattr(e, "link", None),
                            tags=(),
                            impact=0.2,
                            meta={"feed": url}
                        )
                except Exception:
                    pass
            await asyncio.sleep(self.poll_seconds)

class GDELTCollector:
    """Exemplo de coletor (skeleton). Você pode implementar chamadas reais depois."""
    def __init__(self, query: str = "central bank OR inflation", poll_seconds: int = 120):
        self.query = query
        self.poll_seconds = poll_seconds
        self._seen: set[str] = set()

    async def stream(self) -> AsyncIterator[NewsEvent]:
        # Mantido como skeleton para evitar dependência de formato.
        # Aqui você implementa a chamada HTTP para o endpoint que preferir.
        while True:
            await asyncio.sleep(self.poll_seconds)
            # placeholder: nenhum evento
            if False:
                yield NewsEvent(ts=datetime.now(timezone.utc), source="GDELT", title="...", url=None)
