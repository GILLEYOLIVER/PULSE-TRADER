# Testing

Validated on Windows with Python 3.12.10 and SQLite 3.49.1.

```powershell
python -m unittest discover -s tests -v
python -m compileall -q trading_assistant
python -m scripts.smoke_gui
python -m trading_assistant.v2.cli diagnose
```

181 tests passed without skips. Initial-risk model coverage verifies exact paid-entry/initial-stop
cash labels, invariant targets under quantity scaling, unchanged classifier weights, preserved gap
tails, mandatory checked risk units, per-variant model provenance and final materialization.
Date-cache coverage verifies that changed monetary values at the same timestamp immediately change risk blocks.
Cash-risk coverage reproduces and fixes the ordinary short-stop fee
breach, verifies rounded adverse entry reservations, filled-price semantics, remaining stop cash,
legacy pending reservations, invalid prices and uncapped exit-gap losses. Net-score coverage verifies unchanged classifier results, correct per-variant
model-checksum provenance, unfavorable
cash despite high win frequency, untrimmed negative tails, zero-score numeric tolerance, integrity and
pre-external model materialization. Provider-recovery coverage verifies bounded same-URL retries,
persisted Retry-After deadlines, deferred unstarted groups, no reservation after a failed training download
and continued exclusion after a failed external request. Larger-history coverage verifies chunk boundaries, interrupted-download
recovery, corruption rejection without silent replacement, whole-window gap counts, future/size/disk guards
and unchanged normal-provider limits. Teacher-prefix coverage verifies pre-validation-only inputs,
minimum sample/class counts, identical cached model fitting and rejection of mismatched data or parameters.
Multi-timeframe coverage verifies partial-bucket exclusion,
both-direction regime confirmation, unchanged proposal prices/stops/targets, enough retained context,
history-only warmup and bounded opt-in research grids. Archived-reference coverage verifies execution of different preserved
source implementations, exact financial/decision equivalence, source corruption rejection, reference
restoration after unvalidated rebases, and rejection of changed capital/risk/cost/unit assumptions.
Trade-outcome coverage includes realized-label availability,
teacher feature capture without execution changes, deterministic fitting, source/time/parameter compatibility,
model integrity, history-only context, common validation folds and all-or-nothing invalid batch rejection.
Research-cycle coverage includes weighted operation accuracy,
small-sample uncertainty, strict goal evidence, isolated historical windows, immutable versions,
frozen source workspaces, complete runtime archives, cost-stress promotion gates, causal filters,
bounded mean-reversion stops, legacy exposure compatibility, explicit candle gaps and metrics-only replay equivalence.
The suite covers contract value sizing, budget below one lot, fees/exposure, daily/weekly/monthly blocks,
profit stop, stale data, duplicate orders, manual oversizing, conservative barriers and gaps, sell trades,
partial IOC fill, zero liquidity, cancel, disconnect/reconnect, emergency, rollback after injected failures,
positions/blocks across restart, revised candles, invalid values, CSV roundtrip, aggregation, reproducibility,
time partitions, ML checksums, denied real integration methods, and pending-order cancellation after a data gap
while retaining protective stops on existing positions. Additional cases reject fractional risk counts,
mixed CSV origin/timeframe, incompatible ML series and conflicting requested quantities under one idempotency key.
User-supplied session rules block entries on holidays while leaving protective exits active.
Saved risk, execution, strategy and calendar assumptions are immutable in memory.
Suggestions coverage includes both profiles and directions, exclusion of open/future candles,
flat/short-history abstention, metadata/overlap/revision rejection, unsupported instruments,
durable idempotent proposals without orders, and data provenance/tick rounding.

The first run found four sandbox temporary-directory access errors. Tests were changed to create their
isolated temporary directories under the project; none were skipped. Subsequent suite runs passed.
The GUI smoke builds the real Tk window, applies the risk form, steps 80 candles, renders chart, zooms/pans, changes theme/timeframe,
and activates the persistent emergency. It uses a temporary ledger and closes the window cleanly.
The same GUI smoke passed after local installation of CustomTkinter 6.0.0 and Pillow 13.0.0;
the standard Tk fallback had already passed. This checks window creation and core controls, not every visual state.
`scripts/install.ps1 -Ui` completed successfully and the diagnostic reported `customtkinter: true` and `live: DISABLED`.
The GUI smoke also applied the user-supplied calendar through the advanced settings JSON.
It also checks both Suggestions profiles, multi-file import and catalog reload, proposal storage
without orders, replay-only history and JSON export. Set `PULSE_SMOKE_SCREENSHOT` to an output PNG path
to capture the temporary application window; all data remain isolated from the normal ledger.

End-to-end CLI runs: 1,000-bar deterministic demo, CSV replay, 500-bar walk-forward, 300-bar model training
and fixed-grid sensitivity. Reports contain source/hash/parameters. This checks mechanics, not profitability.
An additional 250-bar synthetic demo with a user-supplied holiday calendar recorded the calendar in its report
and produced zero B3 entries on the blocked day.
The calendar option also completed one walk-forward fold and a nine-point sensitivity run on synthetic data.
The sample model underperformed simple baselines on its synthetic holdout; it remains advisory and disabled
for execution regardless of scores. No market-quality or out-of-sample profitability claim is made.

OHLC exits cannot resolve event order; stop-first and gap-aware rules are deliberately conservative.
Entry liquidity is estimated from the PREVIOUS candle, avoiding future volume in an opening fill.
Concurrency is serialized in SQLite; the desktop processes events on its main thread.
Backtests, ML, data downloads and research run on daemon workers; Tk callbacks stay on the main thread.
The portable self-test covers forms, catalog-to-replay preparation, plan arming/cancellation, backup/restore,
background callbacks and embedded SQLite. Public real-data PETR4/VALE3 studies were also executed;
all evidence/calibration gates failed and no model was promoted. See UPGRADE_6_STEPS.md.

Required future operational validation: licensed B3 historical data, official contract/calendar checks,
scenario coverage for auctions/halts, larger portfolios, stress testing, dependency audit, and broker sandbox.
The current source cannot send real orders.

`python -m scripts.stress_cash_risk --cases 10000` exercises synthetic accounting with both directions,
varying ticks, point values, lot sizes, fees, spreads, slippage, entry gaps and explicit exit gaps.
The recorded seed 20261021 checked 5,549 accepted reservations and 5,503 closed positions: 4,949 ordinary
stops stayed within budget and 554 exit gaps retained their full independently calculated losses,
including 493 above budget. There were 4,451 submission rejections and 46 subsequent fill rejections.
No accounting assertion failed. These are mechanics checks, never market win-rate or goal evidence.
See CASH_RISK_ACCOUNTING.md for the original reproduction and reproducible report paths.

An isolated before/after/after/before replay benchmark used the same 3,000 known BTC candles and
recorded exactly identical hashes of metrics, all orders, all trades, equity and training labels.
The median replay time changed from 8.5793s to 4.2284s (2.029x throughput) on this machine while
other research was active. It verifies the pending-only sort and bounded pure-date cache, not a
universal speed guarantee or market improvement. See REPLAY_OVERHEAD.md.
