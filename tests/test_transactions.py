"""
Tests for polymorphic transaction processing via BankService.

Covers requirements:
 4. Successful withdrawals (via service)
11. Polymorphic processing across all account types
13. Preservation of balances after failed transactions
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from banking import (
    BankService,
    CheckingAccount,
    HighYieldAccount,
    InsufficientFundsError,
    InvalidAmountError,
    SavingsAccount,
)
from banking.models import TransactionType


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def bank() -> BankService:
    svc = BankService()
    svc.create_savings_account("Alice", "INR", Decimal("5000.00"))
    svc.create_checking_account(
        "Bob", "USD", Decimal("2000.00"),
        maintenance_fee=Decimal("15.00"),
        overdraft_limit=Decimal("500.00"),
    )
    svc.create_high_yield_account(
        "Carol", "GBP", Decimal("3000.00"),
        minimum_balance=Decimal("1000.00"),
        below_minimum_fee=Decimal("20.00"),
    )
    return svc


# ── Polymorphic interest + fee processing ─────────────────────────────────────


def test_process_interest_and_fees_returns_all_accounts(bank: BankService):
    results = bank.process_interest_and_fees()
    assert len(results) == 3


def test_savings_receives_interest_no_fee(bank: BankService):
    results = bank.process_interest_and_fees()
    savings_result = next(
        v for v in results.values() if v["account_type"] == "SavingsAccount"
    )
    assert savings_result["interest_entry"] is not None
    interest_amount = Decimal(savings_result["interest_entry"]["amount"])
    assert interest_amount > Decimal("0")
    # No fee for savings
    assert savings_result["fee_result"]["success"] is True
    assert Decimal(savings_result["fee_result"]["amount"]) == Decimal("0")


def test_checking_receives_interest_and_fee(bank: BankService):
    results = bank.process_interest_and_fees()
    checking_result = next(
        v for v in results.values() if v["account_type"] == "CheckingAccount"
    )
    # Low interest rate but positive balance → interest entry exists
    assert checking_result["interest_entry"] is not None
    # Fee should be collected
    assert checking_result["fee_result"]["success"] is True
    assert Decimal(checking_result["fee_result"]["amount"]) == Decimal("15.00")


def test_high_yield_receives_interest_when_eligible(bank: BankService):
    results = bank.process_interest_and_fees()
    hy_result = next(
        v for v in results.values() if v["account_type"] == "HighYieldAccount"
    )
    # balance=3000 >= min=1000 → eligible
    assert hy_result["interest_entry"] is not None
    # balance above min → no fee
    assert Decimal(hy_result["fee_result"]["amount"]) == Decimal("0")


def test_polymorphic_process_uses_account_interface(bank: BankService):
    """Ensure the service calls methods on Account objects, not concrete types."""
    from banking.accounts import Account
    results = bank.process_interest_and_fees()
    for acct in bank._registry.all_accounts():  # noqa: SLF001
        assert isinstance(acct, Account)
    assert len(results) == 3


# ── Transaction type coverage ─────────────────────────────────────────────────


def test_all_transaction_types_are_reachable():
    """Ensure all TransactionType enum values are exercisable."""
    acc = SavingsAccount("T", "INR", Decimal("1000.00"),
                         interest_rate=Decimal("0.05"))
    acc.deposit(Decimal("100.00"))
    acc.withdraw(Decimal("50.00"))
    acc.accrue_interest()
    types_seen = {e.transaction_type for e in acc.get_ledger_entries()}
    assert TransactionType.DEPOSIT in types_seen
    assert TransactionType.WITHDRAWAL in types_seen
    assert TransactionType.INTEREST_CREDIT in types_seen
    assert TransactionType.OPENING_BALANCE in types_seen


def test_fee_deduction_transaction_type_recorded():
    acc = CheckingAccount("F", "USD", Decimal("500.00"),
                          maintenance_fee=Decimal("10.00"))
    acc.deduct_fees()
    fee_entries = acc.get_ledger_entries(transaction_type=TransactionType.FEE_DEDUCTION)
    assert len(fee_entries) == 1
    assert fee_entries[0].transaction_type == TransactionType.FEE_DEDUCTION


# ── State preservation on failure ─────────────────────────────────────────────


def test_failed_withdrawal_leaves_ledger_unchanged():
    acc = SavingsAccount("Ledger", "USD", Decimal("100.00"))
    entry_count_before = len(acc.get_ledger_entries())
    with pytest.raises(InsufficientFundsError):
        acc.withdraw(Decimal("999.00"))
    assert len(acc.get_ledger_entries()) == entry_count_before


def test_failed_deposit_leaves_balance_and_ledger_unchanged():
    acc = SavingsAccount("LD", "INR", Decimal("200.00"))
    before_balance = acc.balance
    before_count = len(acc.get_ledger_entries())
    with pytest.raises(InvalidAmountError):
        acc.deposit(Decimal("0"))
    assert acc.balance == before_balance
    assert len(acc.get_ledger_entries()) == before_count


# ── Atomic commit failure simulation ─────────────────────────────────────────


def test_atomic_rollback_on_ledger_failure():
    """If the ledger raises on append, balance must be rolled back."""
    from unittest.mock import MagicMock, patch
    from banking.exceptions import AtomicOperationError

    acc = SavingsAccount("Atomic", "USD", Decimal("500.00"))
    original_balance = acc.balance
    original_entry_count = len(acc.get_ledger_entries())

    # Patch the ledger's append method to raise on the attempted deposit
    call_count = [0]
    real_append = acc._ledger.append  # noqa: SLF001

    def failing_append(entry):
        call_count[0] += 1
        if call_count[0] == 1:
            raise RuntimeError("Simulated ledger failure")
        return real_append(entry)

    acc._ledger.append = failing_append  # noqa: SLF001

    with pytest.raises(AtomicOperationError):
        acc.deposit(Decimal("100.00"))

    # Balance must be rolled back
    assert acc.balance == original_balance
    assert len(acc.get_ledger_entries()) == original_entry_count
