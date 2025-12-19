from __future__ import annotations
import asyncio
from dataclasses import dataclass
from typing import Generic, TypeVar, AsyncIterator

T = TypeVar("T")

@dataclass
class Topic(Generic[T]):
    name: str
    queue: asyncio.Queue[T]

class EventBus:
    def __init__(self):
        self._topics: dict[str, Topic] = {}

    def topic(self, name: str, maxsize: int = 5000) -> Topic:
        if name not in self._topics:
            self._topics[name] = Topic(name=name, queue=asyncio.Queue(maxsize=maxsize))
        return self._topics[name]

    async def publish(self, topic: str, item):
        t = self.topic(topic)
        await t.queue.put(item)

    async def subscribe(self, topic: str) -> AsyncIterator:
        t = self.topic(topic)
        while True:
            item = await t.queue.get()
            yield item
