from __future__ import annotations
import asyncio
import threading
from datetime import datetime, timezone

from trader_tool.config.settings import Settings
from trader_tool.app.logging_setup import setup_logging
from trader_tool.pipeline.bus import EventBus
from trader_tool.adapters.sim_feed import SimFeed
from trader_tool.app.engine import TradingEngine
from trader_tool.app.runner import EngineRunner
from trader_tool.app.ui_ctk import PulseUI

def main():
    setup_logging("INFO")
    settings = Settings()

    bus = EventBus()

    # engine
    engine = TradingEngine(
        bus=bus,
        symbols=list(settings.SYMBOLS),
        settings=settings,
        status_cb=None
    )

    # UI
    runner: EngineRunner | None = None
    handle = {"h": None}

    def start_engine():
        nonlocal runner
        if handle["h"] is not None:
            return
        runner = EngineRunner(engine)
        h = runner.start()
        handle["h"] = h

        # feed simulado e (opcional) news generator rodam no loop do engine
        def feed_task():
            # aguarda loop subir
            import time
            time.sleep(0.3)
            loop = runner._loop
            if not loop:
                return

            async def _producer():
                feeds = [SimFeed(symbol=s, start_price=100_000.0, tick_size=settings.TICK_SIZE) for s in settings.SYMBOLS]
                streams = [f.stream() for f in feeds]
                while not engine._stop.is_set():
                    for st in streams:
                        tick = await st.__anext__()
                        await bus.publish("ticks", tick)

            asyncio.run_coroutine_threadsafe(_producer(), loop)

        threading.Thread(target=feed_task, daemon=True).start()

    def stop_engine():
        if handle["h"] is None:
            return
        handle["h"].stop_fn()
        handle["h"] = None

    ui = PulseUI(on_start=start_engine, on_stop=stop_engine)
    engine.status_cb = ui.push_status
    ui.mainloop()

if __name__ == "__main__":
    main()
