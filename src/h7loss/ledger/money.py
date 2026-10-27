"""Reserve before dispatch; retain unknown usage indefinitely until reconciled.

SQLite is authoritative. Callers must use one database for the lifetime of the app;
opening a second database does not constitute a new spending authorization.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Iterator

APP_CEILING_MICRO_USD = 40_000_000


class LedgerError(ValueError):
    """Invalid operation, exhausted capacity, or reconciliation required."""


def _amount(value: int, label: str) -> int:
    if type(value) is not int or value < 0 or value > APP_CEILING_MICRO_USD:
        raise LedgerError(f"{label} must be an integer from 0 to 40000000 microUSD")
    return value


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


class Ledger:
    """Explicit-path SQLite ledger; no credentials or implicit file discovery.

    Reservation IDs identify individual attempts, including repairs. Reusing an ID
    with different provenance/liability refuses. ``mark_dispatch`` prevents a
    retry from silently making a second call under an old reservation.
    """

    def __init__(self, path: str | Path, cap_micro_usd: int = APP_CEILING_MICRO_USD):
        cap = _amount(cap_micro_usd, "cap")
        if not str(path):
            raise LedgerError("explicit ledger path required")
        self._lock = RLock()
        self._db = sqlite3.connect(str(path), timeout=15, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA foreign_keys=ON")
        self._db.execute("PRAGMA synchronous=FULL")
        self._db.executescript("""
            CREATE TABLE IF NOT EXISTS policy (
              singleton INTEGER PRIMARY KEY CHECK(singleton=1),
              cap INTEGER NOT NULL CHECK(cap>=0 AND cap<=40000000),
              frozen INTEGER NOT NULL DEFAULT 0 CHECK(frozen IN (0,1)));
            CREATE TABLE IF NOT EXISTS attempts (
              attempt_id TEXT PRIMARY KEY, reserved INTEGER NOT NULL,
              actual INTEGER, dispatched INTEGER NOT NULL DEFAULT 0,
              usage_state TEXT NOT NULL, provenance TEXT NOT NULL,
              created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS events (
              sequence INTEGER PRIMARY KEY AUTOINCREMENT,
              attempt_id TEXT NOT NULL REFERENCES attempts(attempt_id),
              kind TEXT NOT NULL, detail TEXT NOT NULL, recorded_at TEXT NOT NULL);
        """)
        with self._transaction():
            row = self._db.execute("SELECT cap FROM policy WHERE singleton=1").fetchone()
            if row is None:
                self._db.execute("INSERT INTO policy(singleton,cap) VALUES(1,?)", (cap,))
            elif row["cap"] != cap:
                raise LedgerError("persisted lifetime cap differs; no implicit reset/change")

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                yield
            except BaseException:
                self._db.execute("ROLLBACK")
                raise
            else:
                self._db.execute("COMMIT")

    def _event(self, attempt_id: str, kind: str, detail: dict[str, Any]) -> None:
        self._db.execute(
            "INSERT INTO events(attempt_id,kind,detail,recorded_at) VALUES(?,?,?,?)",
            (attempt_id, kind, _json(detail), datetime.now(timezone.utc).isoformat()),
        )

    def _totals(self) -> tuple[int, int]:
        row = self._db.execute("""
            SELECT COALESCE(SUM(actual),0) AS spent,
              COALESCE(SUM(CASE WHEN actual IS NULL THEN reserved ELSE 0 END),0) AS held
            FROM attempts
        """).fetchone()
        return int(row["spent"]), int(row["held"])

    def reserve(self, attempt_id: str, max_liability: int,
                provenance: dict[str, Any]) -> dict[str, Any]:
        liability = _amount(max_liability, "max_liability")
        if not isinstance(attempt_id, str) or not attempt_id.strip() or len(attempt_id) > 256:
            raise LedgerError("bounded nonempty attempt_id required")
        if not isinstance(provenance, dict) or not provenance:
            raise LedgerError("nonempty attempt provenance required")
        encoded = _json(provenance)
        with self._transaction():
            old = self._db.execute("SELECT * FROM attempts WHERE attempt_id=?", (attempt_id,)).fetchone()
            if old is not None:
                if old["reserved"] != liability or old["provenance"] != encoded:
                    raise LedgerError("attempt ID conflict")
                return dict(old)
            policy = self._db.execute("SELECT * FROM policy WHERE singleton=1").fetchone()
            spent, held = self._totals()
            if policy["frozen"] or spent + held + liability > policy["cap"]:
                raise LedgerError("ledger frozen or insufficient lifetime capacity")
            self._db.execute("""
                INSERT INTO attempts(attempt_id,reserved,usage_state,provenance,created_at)
                VALUES(?,?,'reserved',?,?)
            """, (attempt_id, liability, encoded, datetime.now(timezone.utc).isoformat()))
            self._event(attempt_id, "reserve", {"max_liability_micro_usd": liability})
            return dict(self._db.execute("SELECT * FROM attempts WHERE attempt_id=?", (attempt_id,)).fetchone())

    def mark_dispatch(self, attempt_id: str) -> None:
        with self._transaction():
            policy = self._db.execute("SELECT frozen FROM policy WHERE singleton=1").fetchone()
            row = self._db.execute("SELECT * FROM attempts WHERE attempt_id=?", (attempt_id,)).fetchone()
            if row is None or row["dispatched"] or row["usage_state"] != "reserved" or policy["frozen"]:
                raise LedgerError("dispatch requires fresh reservation and unfrozen ledger")
            self._db.execute("UPDATE attempts SET dispatched=1 WHERE attempt_id=?", (attempt_id,))
            self._event(attempt_id, "dispatch", {})

    def settle(self, attempt_id: str, usage: int | None,
               receipt: dict[str, Any]) -> dict[str, Any]:
        """None means unknown, never zero. Known usage needs a provider receipt.

        Over-reservation usage is recorded as actual evidence and permanently
        freezes dispatch. It is not silently truncated to make totals look safe.
        """
        if usage is not None:
            if type(usage) is not int or not 0 <= usage <= 9_223_372_036_854_775_807:
                raise LedgerError("usage must be nonnegative integer microUSD within SQLite range")
        if not isinstance(receipt, dict) or not receipt:
            raise LedgerError("nonempty settlement receipt required")
        encoded_receipt = _json(receipt)
        with self._transaction():
            row = self._db.execute("SELECT * FROM attempts WHERE attempt_id=?", (attempt_id,)).fetchone()
            if row is None or not row["dispatched"]:
                raise LedgerError("cannot settle an undispatched/missing attempt")
            if row["actual"] is not None:
                if row["actual"] != usage:
                    raise LedgerError("settlement conflict")
                return dict(row)
            breached = usage is not None and usage > row["reserved"]
            state = "unknown" if usage is None else ("liability_breach" if breached else "settled")
            self._db.execute("UPDATE attempts SET actual=?,usage_state=? WHERE attempt_id=?", (usage, state, attempt_id))
            self._event(attempt_id, state, {"usage_micro_usd": usage, "receipt": json.loads(encoded_receipt)})
            spent, held = self._totals()
            cap = self._db.execute("SELECT cap FROM policy WHERE singleton=1").fetchone()["cap"]
            if breached or spent + held > cap:
                self._db.execute("UPDATE policy SET frozen=1 WHERE singleton=1")
                self._event(attempt_id, "liability_breach", {"spent": spent, "held": held})
            return dict(self._db.execute("SELECT * FROM attempts WHERE attempt_id=?", (attempt_id,)).fetchone())

    def report(self) -> dict[str, Any]:
        with self._transaction():
            policy = self._db.execute("SELECT * FROM policy WHERE singleton=1").fetchone()
            spent, held = self._totals()
            attempts = [dict(row) for row in self._db.execute("SELECT * FROM attempts ORDER BY created_at,attempt_id")]
            events = [dict(row) for row in self._db.execute("SELECT * FROM events ORDER BY sequence")]
            return {"currency": "microUSD", "cap": policy["cap"], "spent": spent,
                    "held": held, "remaining": max(0, policy["cap"] - spent - held),
                    "frozen": bool(policy["frozen"]), "attempts": attempts, "events": events,
                    "snapshot_sha256": hashlib.sha256(_json([attempts, events]).encode()).hexdigest()}

    def close(self) -> None:
        with self._lock:
            self._db.close()
