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

@dataclass(frozen=True)
class SessionCalendar:
    """User-supplied session rules; `verified` is the user's assertion, not B3 certification."""
    holidays: set[date]=field(default_factory=set)
    start: time=time(9)
    end: time=time(18)
    verified: bool=False

    def __post_init__(self):
        if not isinstance(self.holidays,(set,frozenset)):
            raise ValueError("Holidays must be a set of dates")
        object.__setattr__(self,"holidays",frozenset(self.holidays))
        if (type(self.verified) is not bool or not isinstance(self.start,time) or not isinstance(self.end,time)
            or self.start.tzinfo is not None or self.end.tzinfo is not None or self.start>=self.end
            or any(type(day) is not date for day in self.holidays)):
            raise ValueError("Invalid user-supplied session calendar")

    def to_config(self):
        return {"holidays":sorted(day.isoformat() for day in self.holidays),
                "start":self.start.isoformat(),"end":self.end.isoformat(),"verified":self.verified}

    @classmethod
    def from_config(cls,config):
        return cls(holidays={date.fromisoformat(day) for day in config["holidays"]},
                   start=time.fromisoformat(config["start"]),end=time.fromisoformat(config["end"]),
                   verified=config["verified"])

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
