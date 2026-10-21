# PAPER cash-risk accounting

## Corrected failure

The pre-fix source `cd1a10d` could slightly undersize proportional exit fees for a SELL stop: sizing
charged the fee at the nominal stop while execution charged it at the adverse exit price.
A reproducible synthetic case with budget 130.5696, entry 99.8, stop 101, tick 0.1,
one tick of slippage and 10 basis points per side filled 87 units and lost 130.5783.
The ordinary stop loss exceeded its budget by 0.0087; no adverse exit gap was involved.

The corrected same case fills 86 units and loses 129.0774, including actual entry and exit fees.
The original reproduction remains in
`runtime/aprendizado/ciclos/audits/short-stop-fee-repro-20261021.json` and
`reports/numeric-short-stop-reproduction.json`; it is not rewritten as a successful run.

## Shared accounting rules

- Forecast entry uses adverse spread/slippage and adverse tick rounding, exactly as actual fills.
- An explicitly supplied fill price already includes entry costs, even when it equals the signal price.
- Stop risk and target return use adverse exit prices and fees at those prices for both directions.
- Pending orders reserve this stop cash and forecast notional exposure; a restart refreshes old
  reservations in the same ledger transaction without rewriting requested quantity or executed trades.
- Remaining stop cash compares marked net value with net liquidation at the stop, or at an already
  worse mark, including the actually paid entry fee and the adverse exit fee.
- Cancellation, rejection and execution release both cash-risk and notional reservations.
- Invalid/nonpositive adverse prices are rejected before creating new exposure.
- Exit gaps retain the full actual loss. A stop budget is not a guaranteed maximum loss.

These changes apply to future executions. Frozen research workspaces, earlier financial reports,
model labels and archived references retain their original implementations and assumptions.

## Verification on 2026-10-21

The complete 173-test suite passed without skips, as did compilation and the actual dashboard smoke.
Seven new cases cover the original failure, both entry-price modes, reservations, remaining risk,
restart compatibility, invalid prices and an uncapped adverse exit gap.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m compileall -q trading_assistant
.\.venv\Scripts\python.exe -m scripts.smoke_gui
.\.venv\Scripts\python.exe -m scripts.stress_cash_risk --cases 10000 --seed 20261021 --output reports/numeric-risk-stress-20261021.json
```

The stress runner compares actual engine fills and ledger cash with independent fee/P&L arithmetic.
It varies direction, tick, multiplier, lot, margin, fixed/proportional fee, spread, slippage and entry gap.
Its 10,000 seeded synthetic cases produced:

| Check | Cases |
| --- | ---: |
| Accepted reservations checked | 5,549 |
| BUY / SELL positions closed | 2,726 / 2,777 |
| Ordinary stops within initial budget | 4,949 |
| Exit gaps with full actual cash preserved | 554 |
| Gap losses above budget, preserved | 493 |
| Submission / subsequent fill rejections | 4,451 / 46 |
| Failed accounting assertions | 0 |

The largest ordinary loss/budget ratio was 0.9999999512455275. This is a numeric accounting ratio,
not market accuracy. The synthetic outcomes are excluded from research training, promotion and
the more-than-90% goal. Real chronological external evidence is still required.
