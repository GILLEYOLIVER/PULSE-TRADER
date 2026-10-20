from __future__ import annotations
from dataclasses import dataclass,field
from datetime import date,datetime,time,timedelta,timezone
try:
    from zoneinfo import ZoneInfo
    SAO_PAULO=ZoneInfo("America/Sao_Paulo")
except Exception:
    # Current Brazil has no DST. Explicit fallback for Windows without tzdata.
    SAO_PAULO=timezone(timedelta(hours=-3),"America/Sao_Paulo fixed UTC-3")

def local_time(ts): return ts.astimezone(SAO_PAULO)

@dataclass
class SessionCalendar:
    """User-provided exchange calendar. Weekdays alone are not an official B3 calendar."""
    holidays: set[date]=field(default_factory=set)
    start: time=time(9)
    end: time=time(18)
    verified: bool=False

    def is_open(self,ts,symbol):
        if symbol in ("BTC","ETH"): return True
        if not self.verified: return False
        local=local_time(ts)
        return local.weekday()<5 and local.date() not in self.holidays and self.start<=local.time()<self.end

    def validate_contract(self,instrument,ts):
        # Explicit expiry metadata only; no guessed continuous-contract rollover.
        if instrument.expiry and local_time(ts).date()>=date.fromisoformat(instrument.expiry):
            return False
        return True
