"""Deliberately disabled official broker boundary; does not load a DLL or send network requests."""
from typing import Protocol

class BrokerPort(Protocol):
    def balances(self) -> dict: ...
    def positions(self) -> list: ...
    def submit(self,order) -> dict: ...
    def cancel(self,order_id) -> dict: ...
    def reconcile(self) -> dict: ...

class RicoProfitAdapter:
    available=False
    reason="Rico/ProfitDLL routing entitlement, official SDK, contract and sandbox not verified. LIVE disabled in this release."
    def _disabled(self,*args,**kwargs): raise PermissionError(self.reason)
    balances=_disabled
    positions=_disabled
    submit=_disabled
    cancel=_disabled
    reconcile=_disabled
