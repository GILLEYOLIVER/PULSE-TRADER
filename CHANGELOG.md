# Changelog

## Unreleased

- Reject reuse of a paper order idempotency key when its stop, target, expiry, or strategy changes.
- Reject conflicting requested quantities for an existing paper order key.
- Enforce whole-number execution limits and consistent CSV/ML data source and timeframe.
- Add optional user-verified session calendar to paper entries, backtests, CLI and dashboard JSON.
- Validate the desktop smoke path with locally installed CustomTkinter and Pillow.
- Add a Windows `-Ui` install option for the two optional dashboard packages.
- Keep saved risk, execution, strategy and calendar assumptions immutable during a paper session.

## 2.0.1 - 2026-10-20

- Added simple controls for core PAPER limits and strategy, with the full JSON configuration retained.
- Cancelled pending entries after missing candles, without skipping protective exits; audited the gap.
- Added regression coverage for gaps and GUI smoke coverage for the risk form.
- Chart periods are shown in minutes, restricted to the imported data granularity, and labeled in Brasilia time.

## 2.0.0 — 2026-10-20

- Added isolated PAPER domain with historical CSV and deterministic synthetic providers.
- Added explainable indicator strategies, multi-timeframe filter, persisted risk/order/position ledger.
- Added next-candle execution, IOC partials, costs, gaps, protective exits and persistent emergency.
- Added reproducible backtests, walk-forward, sensitivity, per-regime results and optional temporal ML.
- Added desktop dashboard with Tk fallback, risk/settings JSON, charts and reports, Windows scripts.
- Disabled legacy execution bypass and all LIVE entry points; redacted secrets from audit logging.
- Corrected legacy news bias and synthetic training timestamps; retained previous analysis modules.
- Documented Rico/ProfitDLL requirements and unresolved external entitlements; no broker SDK binding shipped.

## 0.1.0

- Original CustomTkinter dashboard, news integrations, technical signals and shadow performance tracking.
