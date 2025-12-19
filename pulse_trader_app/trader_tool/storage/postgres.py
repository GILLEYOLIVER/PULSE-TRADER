from __future__ import annotations
import json
import logging
from pathlib import Path
from typing import Optional
import psycopg2
from psycopg2.extras import Json
from trader_tool.domain.models import Signal, ApprovedTrade, Fill

logger = logging.getLogger("pulse.store")

class PostgresStore:
    def __init__(self, dsn: str, schema_sql_path: Optional[str] = None):
        self.dsn = dsn
        self.schema_sql_path = schema_sql_path or str(Path(__file__).with_name("schema.sql"))

    def _conn(self):
        return psycopg2.connect(self.dsn)

    def ensure_schema(self):
        sql = Path(self.schema_sql_path).read_text(encoding="utf-8")
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
        logger.info("Schema pulse garantido no PostgreSQL.")

    def save_signal(self, s: Signal):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO pulse.signals(ts, symbol, side, confidence, rationale, meta)
                       VALUES (%s,%s,%s,%s,%s,%s)""",
                    (s.ts, s.symbol, s.side.value, float(s.confidence), s.rationale, Json(s.meta or {}))
                )

    def save_approved(self, t: ApprovedTrade):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO pulse.trades_approved(ts, symbol, side, contracts, entry_hint, stop_price, target_price, risk_amount, rationale, meta)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (t.ts, t.symbol, t.side.value, int(t.contracts), float(t.entry_hint), float(t.stop_price),
                     float(t.target_price) if t.target_price is not None else None,
                     float(t.risk_amount), t.rationale, Json(t.meta or {}))
                )

    def save_fill(self, f: Fill):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO pulse.fills(ts, symbol, side, contracts, price, fees, meta)
                       VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                    (f.ts, f.symbol, f.side.value, int(f.contracts), float(f.price), float(f.fees), Json(f.meta or {}))
                )

    def save_pnl_event(self, ts, symbol: str, realized_pnl: float, was_stop: bool):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO pulse.pnl_events(ts, symbol, realized_pnl, was_stop)
                       VALUES (%s,%s,%s,%s)""",
                    (ts, symbol, float(realized_pnl), bool(was_stop))
                )
