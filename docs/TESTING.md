# Testing

Validated on Windows with Python 3.12.10 and SQLite 3.49.1.

```powershell
python -m unittest discover -s tests -v
python -m compileall -q trading_assistant
python -m scripts.smoke_gui
python -m trading_assistant.v2.cli diagnose
```

47 tests passed without skips. The suite covers contract value sizing, budget below one lot, fees/exposure, daily/weekly/monthly blocks,
profit stop, stale data, duplicate orders, manual oversizing, conservative barriers and gaps, sell trades,
partial IOC fill, zero liquidity, cancel, disconnect/reconnect, emergency, rollback after injected failures,
positions/blocks across restart, revised candles, invalid values, CSV roundtrip, aggregation, reproducibility,
time partitions, ML checksums, denied real integration methods, and pending-order cancellation after a data gap
while retaining protective stops on existing positions.

The first run found four sandbox temporary-directory access errors. Tests were changed to create their
isolated temporary directories under the project; none were skipped. Subsequent suite runs passed.
The GUI smoke builds the real Tk window, applies the risk form, steps 80 candles, renders chart, zooms/pans, changes theme/timeframe,
and activates the persistent emergency. It uses a temporary ledger and closes the window cleanly.
CustomTkinter could not be installed due DNS, so that optional rendering path was not exercised.

End-to-end CLI runs: 1,000-bar deterministic demo, CSV replay, 500-bar walk-forward, 300-bar model training
and fixed-grid sensitivity. Reports contain source/hash/parameters. This checks mechanics, not profitability.
The sample model underperformed simple baselines on its synthetic holdout; it remains advisory and disabled
for execution regardless of scores. No market-quality or out-of-sample profitability claim is made.

OHLC exits cannot resolve event order; stop-first and gap-aware rules are deliberately conservative.
Entry liquidity is estimated from the PREVIOUS candle, avoiding future volume in an opening fill.
Concurrency is serialized in SQLite; the desktop processes events on its main thread.
Large backtests currently run synchronously from the UI; the CLI is preferable for long studies.

Required future operational validation: licensed B3 historical data, official contract/calendar checks,
scenario coverage for auctions/halts, larger portfolios, stress testing, dependency audit, and broker sandbox.
The current source cannot send real orders.
