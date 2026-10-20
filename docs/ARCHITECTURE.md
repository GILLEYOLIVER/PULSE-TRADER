# Architecture and initial audit

Baseline: upstream main commit 0ded5fbb6461a3ceb296fa016451758e673430d1, 43 files.
Direct clone failed DNS resolution; files were obtained through the authenticated GitHub connector.
Remote publication must use the existing upstream commit as parent, preserving history.

Findings: all prices/orderbook are random; RiskEngine uses price distance without contract multiplier,
forces minimum one unit even above budget, increments trade count on recommendations and can increase
risk using confidence. Manual orders bypass RiskEngine. Router accepts live mode and returns QUEUED
without a real integration. No persistent ledger or critical tests. Signal news penalty is directional
(subtraction favors SELL); confidence is heuristic. Pipeline logs the complete configuration (API keys)
and a serialized report containing datetime cannot be JSON encoded; exceptions are swallowed.
Legacy synthetic training wraps seconds instead of advancing time. Shadow tracker is separate from
risk sizing and omits actual currency costs. UI owns its own state and calculations.

Decision: keep original modules for compatibility, add an independent standard-library v2 domain,
SQLite unit of work, deterministic historical/synthetic feeds, strategy registry, conservative execution,
CLI/backtest and desktop controller. New default UI uses CustomTkinter if installed, otherwise Tk.
No dependency on network is required for analysis/paper. All v2 state belongs to the controller;
Tk callbacks stay on the UI thread. SQLite transactions provide crash atomicity and unique keys.
Broker integration is a disabled boundary, not an invented SDK implementation.
