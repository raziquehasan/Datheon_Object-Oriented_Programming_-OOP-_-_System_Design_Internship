"""
Tests for the financial ledger.

Covers requirements:
12. Ledger entry creation and ordering
13. Preservation of balances after failed transactions
14. Protection against external mutation of ledger entries
"""

from __future__ import annotations

import time
from decimal import Decimal
from unittest.mock import patch

import pytest

from banking import (
    CheckingAccount,
    Ledger,
    SavingsAccount,
)
from banking.exceptions import AtomicOperationError
from banking.models import LedgerEntry, TransactionType


# ── 12. Ledger entry creation and ordering ────────────────────────────────────


def test_opening_balance_creates_ledger_entry():
    acc = SavingsAccount("A", "INR", Decimal("500.00"))
    entries = acc.get_ledger_entries()
    assert len(entries) == 1
    assert entries[0].transaction_type == TransactionType.OPENING_BALANCE
    assert entries[0].amount == Decimal("500.00")


def test_zero_initial_balance_no_opening_entry():
    acc = SavingsAccount("B", "INR", Decimal("0"))
    entries = acc.get_ledger_entries()
    assert len(entries) == 0


def test_ledger_entries_are_chronological():
    acc = SavingsAccount("C", "USD", Decimal("1000.00"))
    acc.deposit(Decimal("100.00"))
    acc.withdraw(Decimal("50.00"))
    entries = acc.get_ledger_entries()
    timestamps = [e.timestamp for e in entries]
    assert timestamps == sorted(timestamps)


def test_each_entry_has_unique_transaction_id():
    acc = SavingsAccount("D", "INR", Decimal("1000.00"))
    acc.deposit(Decimal("100.00"))
    acc.deposit(Decimal("200.00"))
    ids = [e.transaction_id for e in acc.get_ledger_entries()]
    assert len(ids) == len(set(ids))


def test_entry_balance_before_after_fields():
    acc = SavingsAccount("E", "USD", Decimal("0"))
    acc.deposit(Decimal("300.00"))
    acc.withdraw(Decimal("100.00"))
    entries = acc.get_ledger_entries()
    deposit = entries[0]
    assert deposit.balance_before == Decimal("0")
    assert deposit.balance_after == Decimal("300.00")
    withdrawal = entries[1]
    assert withdrawal.balance_before == Decimal("300.00")
    assert withdrawal.balance_after == Decimal("200.00")


def test_entry_account_id_matches_account():
    acc = SavingsAccount("F", "USD", Decimal("100.00"))
    acc.deposit(Decimal("50.00"))
    for entry in acc.get_ledger_entries():
        assert entry.account_id == acc.account_id


def test_entry_currency_matches_account():
    acc = SavingsAccount("G", "EUR", Decimal("100.00"))
    acc.deposit(Decimal("50.00"))
    for entry in acc.get_ledger_entries():
        assert entry.currency == "EUR"


def test_filter_by_transaction_type():
    acc = SavingsAccount("H", "USD", Decimal("1000.00"),
                         interest_rate=Decimal("0.05"))
    acc.deposit(Decimal("100.00"))
    acc.withdraw(Decimal("50.00"))
    acc.accrue_interest()
    deposits = acc.get_ledger_entries(transaction_type=TransactionType.DEPOSIT)
    assert all(e.transaction_type == TransactionType.DEPOSIT for e in deposits)
    assert len(deposits) == 1


def test_filter_by_date_range():
    from datetime import datetime, timezone, timedelta

    acc = SavingsAccount("I", "USD", Decimal("500.00"))
    acc.deposit(Decimal("10.00"))
    mid = datetime.now(timezone.utc)
    time.sleep(0.01)  # ensure timestamp ordering
    acc.deposit(Decimal("20.00"))

    entries_before_mid = acc.get_ledger_entries(end_time=mid)
    entries_after_mid = acc.get_ledger_entries(start_time=mid)

    # The opening+first deposit happened before mid
    assert all(e.timestamp <= mid for e in entries_before_mid)
    # The second deposit happened after mid
    assert all(e.timestamp >= mid for e in entries_after_mid)


# ── 14. Protection against external mutation ──────────────────────────────────


def test_ledger_entry_is_immutable():
    """LedgerEntry is a frozen dataclass; mutation raises FrozenInstanceError."""
    from dataclasses import FrozenInstanceError

    acc = SavingsAccount("J", "USD", Decimal("100.00"))
    acc.deposit(Decimal("50.00"))
    entry = acc.get_ledger_entries()[0]
    with pytest.raises(FrozenInstanceError):
        entry.amount = Decimal("999.00")  # type: ignore[misc]


def test_get_ledger_entries_returns_tuple():
    """Returned object must be a tuple (immutable), not a list."""
    acc = SavingsAccount("K", "USD", Decimal("100.00"))
    result = acc.get_ledger_entries()
    assert isinstance(result, tuple)


def test_modifying_returned_tuple_does_not_affect_ledger():
    """Caller cannot extend the returned collection."""
    acc = SavingsAccount("L", "USD", Decimal("100.00"))
    acc.deposit(Decimal("50.00"))
    entries = acc.get_ledger_entries()
    # Tuples are immutable; this confirms we cannot append
    with pytest.raises((AttributeError, TypeError)):
        entries.append(None)  # type: ignore[attr-defined]


def test_ledger_append_rejects_non_entry():
    """Ledger.append raises TypeError on non-LedgerEntry input."""
    ledger = Ledger()
    with pytest.raises(TypeError):
        ledger.append("not an entry")  # type: ignore[arg-type]


# ── Account isolation ─────────────────────────────────────────────────────────


def test_two_accounts_do_not_share_ledger_entries():
    acc1 = SavingsAccount("M", "USD", Decimal("100.00"))
    acc2 = SavingsAccount("N", "USD", Decimal("200.00"))
    acc1.deposit(Decimal("10.00"))
    acc2.deposit(Decimal("20.00"))
    assert all(e.account_id == acc1.account_id for e in acc1.get_ledger_entries())
    assert all(e.account_id == acc2.account_id for e in acc2.get_ledger_entries())


# ── 13. Failed operations do not create ledger entries ────────────────────────


def test_failed_withdrawal_no_ledger_entry():
    acc = SavingsAccount("O", "USD", Decimal("50.00"))
    from banking.exceptions import InsufficientFundsError

    count_before = len(acc.get_ledger_entries())
    with pytest.raises(InsufficientFundsError):
        acc.withdraw(Decimal("999.00"))
    assert len(acc.get_ledger_entries()) == count_before


def test_failed_deposit_no_ledger_entry():
    acc = SavingsAccount("P", "USD", Decimal("50.00"))
    from banking.exceptions import InvalidAmountError

    count_before = len(acc.get_ledger_entries())
    with pytest.raises(InvalidAmountError):
        acc.deposit(Decimal("-1"))
    assert len(acc.get_ledger_entries()) == count_before


def test_atomic_commit_rollback_no_entry_on_ledger_failure():
    """Simulate ledger failure and verify balance rolls back and entry count is unchanged."""
    acc = SavingsAccount("Q", "USD", Decimal("100.00"))

    # Count initial entries (opening balance)
    initial_count = len(acc.get_ledger_entries())
    original_balance = acc.balance

    # Patch ledger.append to fail on the attempted deposit
    call_count = [0]
    real_append = acc._ledger.append  # noqa: SLF001

    def failing_append(entry):
        call_count[0] += 1
        if call_count[0] == 1:
            raise RuntimeError("Injected ledger failure")
        return real_append(entry)

    acc._ledger.append = failing_append  # noqa: SLF001

    with pytest.raises(AtomicOperationError):
        acc.deposit(Decimal("50.00"))

    assert acc.balance == original_balance
    # No new entry should appear (the failing append was bypassed by rollback)
    # The ledger count is unchanged from before the attempted deposit
    assert len(acc.get_ledger_entries()) == initial_count
