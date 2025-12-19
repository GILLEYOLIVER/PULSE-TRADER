from __future__ import annotations
import asyncio
import threading
from dataclasses import dataclass
from typing import Callable, Optional
from trader_tool.pipeline.bus import EventBus
from trader_tool.app.engine import TradingEngine

@dataclass
class RunnerHandle:
    thread: threading.Thread
    stop_fn: Callable[[], None]

class EngineRunner:
    def __init__(self, engine: TradingEngine):
        self.engine = engine
        self._loop: asyncio.AbstractEventLoop | None = None

    def start(self) -> RunnerHandle:
        def _run():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._loop.run_until_complete(self.engine.run())

        t = threading.Thread(target=_run, daemon=True)
        t.start()

        def stop():
            if self._loop and self._loop.is_running():
                asyncio.run_coroutine_threadsafe(self.engine.stop(), self._loop)

        return RunnerHandle(thread=t, stop_fn=stop)
