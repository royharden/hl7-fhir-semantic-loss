"""Builder-authored accounting regressions, not independent truth or real spend."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from h7loss.ledger import Ledger, LedgerError


@pytest.fixture
def ledger(tmp_path):
    store = Ledger(tmp_path / "developer-ledger.sqlite", cap_micro_usd=100)
    try:
        yield store
    finally:
        store.close()


def test_reservation_replay_is_idempotent_but_request_drift_refuses(ledger):
    """Catches silent extra liability or hidden calls under an old attempt ID."""
    provenance = {"kind": "builder-unit-test", "request_sha256": "a" * 64}
    first = ledger.reserve("attempt-1", 60, provenance)
    assert ledger.reserve("attempt-1", 60, provenance) == first
    for liability, changed in ((61, provenance), (60, {**provenance, "request_sha256": "b" * 64})):
        with pytest.raises(LedgerError, match="conflict"):
            ledger.reserve("attempt-1", liability, changed)
    report = ledger.report()
    assert (report["spent"], report["held"], report["remaining"]) == (0, 60, 40)
    assert len(report["attempts"]) == 1
    assert [event["kind"] for event in report["events"]] == ["reserve"]


def test_dispatch_once_and_settlement_releases_only_known_unused_exposure(ledger):
    ledger.reserve("attempt", 70, {"kind": "builder-unit-test"})
    ledger.mark_dispatch("attempt")
    with pytest.raises(LedgerError, match="fresh reservation"):
        ledger.mark_dispatch("attempt")
    settled = ledger.settle("attempt", 20, {"fixture": "known-usage"})
    assert settled["usage_state"] == "settled"
    assert ledger.report()["remaining"] == 80
    assert ledger.settle("attempt", 20, {"fixture": "idempotent-receipt"}) == settled
    with pytest.raises(LedgerError, match="settlement conflict"):
        ledger.settle("attempt", 0, {"fixture": "cannot-refund-known-spend"})
    assert len([e for e in ledger.report()["events"] if e["kind"] == "dispatch"]) == 1


def test_unknown_usage_holds_liability_until_evidenced_reconciliation(ledger):
    ledger.reserve("unknown", 80, {"kind": "builder-unit-test"})
    ledger.mark_dispatch("unknown")
    assert ledger.settle("unknown", None, {"fixture": "timeout"})["usage_state"] == "unknown"
    report = ledger.report()
    assert (report["spent"], report["held"], report["remaining"]) == (0, 80, 20)
    with pytest.raises(LedgerError, match="capacity"):
        ledger.reserve("too-much", 21, {"kind": "builder-unit-test"})
    ledger.settle("unknown", 25, {"fixture": "later-provider-receipt"})
    report = ledger.report()
    assert (report["spent"], report["held"], report["remaining"]) == (25, 0, 75)
    assert [event["kind"] for event in report["events"]][-2:] == ["unknown", "settled"]


def test_liability_breach_retains_actual_and_permanently_freezes(ledger):
    ledger.reserve("first", 10, {"kind": "builder-unit-test"})
    ledger.reserve("pending", 10, {"kind": "builder-unit-test"})
    ledger.mark_dispatch("first")
    assert ledger.settle("first", 11, {"fixture": "over-bound"})["usage_state"] == "liability_breach"
    report = ledger.report()
    assert report["spent"] == 11 and report["held"] == 10 and report["frozen"] is True
    with pytest.raises(LedgerError):
        ledger.mark_dispatch("pending")
    with pytest.raises(LedgerError):
        ledger.reserve("even-free", 0, {"kind": "builder-unit-test"})


def test_extreme_breach_evidence_does_not_overflow_sqlite_sum(ledger):
    """Catches loss of accounting/report evidence when actuals exceed int64 total."""
    for attempt in ("one", "two"):
        ledger.reserve(attempt, 1, {"kind": "builder-unit-test", "attempt": attempt})
        ledger.mark_dispatch(attempt)
    huge = 9_223_372_036_854_775_807
    for attempt in ("one", "two"):
        ledger.settle(attempt, huge, {"fixture": "synthetic-extreme-liability"})
    report = ledger.report()
    assert report["spent"] == 2 * huge
    assert report["remaining"] == 0 and report["held"] == 0 and report["frozen"] is True


@pytest.mark.parametrize("value", [-1, True, 1.5, "10", 40_000_001])
def test_reservation_requires_bounded_integer_micro_usd(ledger, value):
    with pytest.raises(LedgerError):
        ledger.reserve("invalid", value, {"kind": "builder-unit-test"})
    assert ledger.report()["attempts"] == []


def test_undispatched_or_missing_attempt_cannot_settle(ledger):
    ledger.reserve("reserved", 10, {"kind": "builder-unit-test"})
    for attempt in ("reserved", "missing"):
        with pytest.raises(LedgerError, match="undispatched/missing"):
            ledger.settle(attempt, 0, {"fixture": "not-dispatched"})
    assert ledger.report()["held"] == 10


def test_nonfinite_or_recursive_provenance_is_a_typed_refusal(ledger):
    recursive = {}
    recursive["self"] = recursive
    for provenance in ({"value": float("nan")}, recursive):
        with pytest.raises(LedgerError, match="finite bounded-depth JSON"):
            ledger.reserve("invalid-json", 1, provenance)
    assert ledger.report()["attempts"] == []


def test_app_lifetime_cap_survives_connection_reopen(tmp_path):
    path = tmp_path / "same-lifetime.sqlite"
    original = Ledger(path, cap_micro_usd=100)
    original.reserve("persisted", 80, {"kind": "builder-unit-test"})
    original.close()
    reopened = Ledger(path, cap_micro_usd=100)
    try:
        assert reopened.report()["held"] == 80
        with pytest.raises(LedgerError, match="capacity"):
            reopened.reserve("extra", 21, {"kind": "builder-unit-test"})
    finally:
        reopened.close()
    with pytest.raises(LedgerError, match="persisted lifetime cap differs"):
        Ledger(path, cap_micro_usd=99)


def test_concurrent_connections_cannot_oversubscribe_one_database(tmp_path):
    """Each thread owns its SQLite connection; both reserve against one DB."""
    path = tmp_path / "concurrent.sqlite"
    initial = Ledger(path, cap_micro_usd=100)
    initial.close()
    start = Barrier(2)

    def reserve(attempt):
        connection = Ledger(path, cap_micro_usd=100)
        try:
            start.wait(timeout=10)
            try:
                connection.reserve(attempt, 70, {"kind": "builder-unit-test", "attempt": attempt})
                return "reserved"
            except LedgerError:
                return "refused"
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(reserve, ("thread-one", "thread-two")))
    assert sorted(outcomes) == ["refused", "reserved"]
    final = Ledger(path, cap_micro_usd=100)
    try:
        assert final.report()["held"] == 70
        assert len(final.report()["attempts"]) == 1
    finally:
        final.close()
