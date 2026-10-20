# PULSE-TRADER engineering rules

Keep execution PAPER only. Never add broker credentials, click automation, or live order calls.
Preserve legacy modules and entry points; put the new service layer in trading_assistant/v2.
Risk checks must run for every entry, including manual UI and backtest orders.
Persist fills, positions, limits, and idempotency keys in one SQLite transaction.
Use closed candles only and execute backtest signals on the following candle.
Run python -m unittest discover -s tests -v and python -m compileall -q trading_assistant.
Use Conventional Commits on feature/pulse-trader-v2; no automatic merge.
Do not present synthetic data or heuristic scores as live quotes or calibrated probabilities.
