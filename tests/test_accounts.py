"""
Tests for account creation, deposits, withdrawals, and concurrent safety.

Covers requirements:
 1. Successful account creation
 2. Invalid account names and currencies
 3. Successful deposits
 4. Successful withdrawals
 5. Rejection of invalid monetary amounts
 6. Insufficient-funds handling
 7. Configured overdraft behavior
11. Polymorphic processing across all account types
13. Preservation of balances after failed transactions
16. Concurrent withdrawal safety
18. Abstract-class enforcement
"""

from __future__ import annotations

import threading
from decimal import Decimal

import pytest

from banking import (
    Account,
    BankService,
    CheckingAccount,
    HighYieldAccount,
    InsufficientFundsError,
    InvalidAccountError,
    InvalidAmountError,
    OverdraftLimitExceededError,
    SavingsAccount,
    UnsupportedCurrencyError,
)
from banking.exceptions import AccountConfigurationError


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def savings() -> SavingsAccount:
    return SavingsAccount("Alice", "INR", Decimal("1000.00"))


@pytest.fixture
def checking() -> CheckingAccount:
    return CheckingAccount(
        "Bob",
        "USD",
        Decimal("500.00"),
        maintenance_fee=Decimal("10.00"),
        overdraft_limit=Decimal("200.00"),
    )


@pytest.fixture
def high_yield() -> HighYieldAccount:
    return HighYieldAccount(
        "Carol",
        "GBP",
        Decimal("2000.00"),
        minimum_balance=Decimal("1000.00"),
    )


# ── 18. Abstract-class enforcement ───────────────────────────────────────────


def test_account_is_abstract():
    """Account cannot be instantiated directly."""
    with pytest.raises(TypeError):
        Account("X", "INR")  # type: ignore[abstract]


# ── 1. Successful account creation ───────────────────────────────────────────


def test_savings_account_creation(savings: SavingsAccount):
    assert savings.holder_name == "Alice"
    assert savings.currency == "INR"
    assert savings.balance == Decimal("1000.00")
    assert savings.account_id  # non-empty UUID string


def test_checking_account_creation(checking: CheckingAccount):
    assert checking.holder_name == "Bob"
    assert checking.currency == "USD"
    assert checking.balance == Decimal("500.00")
    assert checking.overdraft_limit == Decimal("200.00")


def test_high_yield_account_creation(high_yield: HighYieldAccount):
    assert high_yield.holder_name == "Carol"
    assert high_yield.currency == "GBP"
    assert high_yield.balance == Decimal("2000.00")


def test_account_creation_with_zero_balance():
    acc = SavingsAccount("Dave", "EUR", Decimal("0"))
    assert acc.balance == Decimal("0")


def test_whitespace_stripped_from_name():
    acc = SavingsAccount("  Eve  ", "USD", Decimal("0"))
    assert acc.holder_name == "Eve"


# ── 2. Invalid account names and currencies ───────────────────────────────────


def test_empty_name_rejected():
    with pytest.raises(InvalidAccountError):
        SavingsAccount("", "INR", Decimal("0"))


def test_whitespace_only_name_rejected():
    with pytest.raises(InvalidAccountError):
        SavingsAccount("   ", "USD", Decimal("0"))


def test_unsupported_currency_rejected():
    with pytest.raises(UnsupportedCurrencyError):
        SavingsAccount("Frank", "XYZ", Decimal("0"))


def test_negative_initial_balance_rejected():
    with pytest.raises(InvalidAmountError):
        SavingsAccount("Grace", "INR", Decimal("-1"))


def test_nan_initial_balance_rejected():
    with pytest.raises(InvalidAmountError):
        SavingsAccount("Henry", "INR", Decimal("NaN"))


def test_infinite_initial_balance_rejected():
    with pytest.raises(InvalidAmountError):
        SavingsAccount("Iris", "USD", Decimal("Infinity"))


def test_float_initial_balance_rejected():
    with pytest.raises(InvalidAmountError):
        SavingsAccount("Jack", "USD", 100.0)  # type: ignore[arg-type]


# ── Account configuration validation ─────────────────────────────────────────


def test_negative_interest_rate_rejected():
    with pytest.raises(AccountConfigurationError):
        SavingsAccount("K", "INR", Decimal("0"), interest_rate=Decimal("-0.01"))


def test_negative_maintenance_fee_rejected():
    with pytest.raises(AccountConfigurationError):
        CheckingAccount("L", "USD", Decimal("0"), maintenance_fee=Decimal("-5"))


def test_negative_overdraft_limit_rejected():
    with pytest.raises(AccountConfigurationError):
        CheckingAccount("M", "USD", Decimal("0"), overdraft_limit=Decimal("-1"))


def test_negative_minimum_balance_rejected():
    with pytest.raises(AccountConfigurationError):
        HighYieldAccount("N", "GBP", Decimal("0"), minimum_balance=Decimal("-1"))


def test_float_interest_rate_rejected():
    with pytest.raises(AccountConfigurationError):
        SavingsAccount("O", "INR", Decimal("0"), interest_rate=0.05)  # type: ignore[arg-type]


# ── 3. Successful deposits ────────────────────────────────────────────────────


def test_deposit_increases_balance(savings: SavingsAccount):
    savings.deposit(Decimal("500.00"))
    assert savings.balance == Decimal("1500.00")


def test_deposit_returns_ledger_entry(savings: SavingsAccount):
    from banking.models import TransactionType
    entry = savings.deposit(Decimal("200.00"))
    assert entry.transaction_type == TransactionType.DEPOSIT
    assert entry.amount == Decimal("200.00")
    assert entry.balance_after == Decimal("1200.00")


def test_deposit_with_description(savings: SavingsAccount):
    entry = savings.deposit(Decimal("100.00"), description="Salary credit")
    assert entry.description == "Salary credit"


# ── 5. Rejection of invalid monetary amounts ─────────────────────────────────


def test_deposit_zero_rejected(savings: SavingsAccount):
    with pytest.raises(InvalidAmountError):
        savings.deposit(Decimal("0"))


def test_deposit_negative_rejected(savings: SavingsAccount):
    with pytest.raises(InvalidAmountError):
        savings.deposit(Decimal("-50.00"))


def test_deposit_nan_rejected(savings: SavingsAccount):
    with pytest.raises(InvalidAmountError):
        savings.deposit(Decimal("NaN"))


def test_deposit_infinity_rejected(savings: SavingsAccount):
    with pytest.raises(InvalidAmountError):
        savings.deposit(Decimal("Infinity"))


def test_deposit_float_rejected(savings: SavingsAccount):
    with pytest.raises(InvalidAmountError):
        savings.deposit(100.0)  # type: ignore[arg-type]


# ── 4. Successful withdrawals ─────────────────────────────────────────────────


def test_withdrawal_decreases_balance(savings: SavingsAccount):
    savings.withdraw(Decimal("400.00"))
    assert savings.balance == Decimal("600.00")


def test_withdrawal_returns_ledger_entry(savings: SavingsAccount):
    from banking.models import TransactionType
    entry = savings.withdraw(Decimal("100.00"))
    assert entry.transaction_type == TransactionType.WITHDRAWAL
    assert entry.amount == Decimal("100.00")


# ── 6. Insufficient-funds handling ────────────────────────────────────────────


def test_savings_overdraft_rejected(savings: SavingsAccount):
    with pytest.raises(InsufficientFundsError):
        savings.withdraw(Decimal("5000.00"))


def test_checking_overdraft_rejected_beyond_limit(checking: CheckingAccount):
    # Balance=500, limit=200 → max=700; 701 should fail
    with pytest.raises(OverdraftLimitExceededError):
        checking.withdraw(Decimal("701.00"))


def test_high_yield_overdraft_rejected(high_yield: HighYieldAccount):
    with pytest.raises(InsufficientFundsError):
        high_yield.withdraw(Decimal("9999.00"))


# ── 7. Configured overdraft behavior ─────────────────────────────────────────


def test_checking_allows_withdrawal_within_overdraft(checking: CheckingAccount):
    # Balance=500, limit=200 → can withdraw 700
    entry = checking.withdraw(Decimal("700.00"))
    assert checking.balance == Decimal("-200.00")
    assert entry.balance_after == Decimal("-200.00")


def test_checking_no_overdraft_by_default():
    acc = CheckingAccount("P", "USD", Decimal("100.00"), overdraft_limit=Decimal("0"))
    with pytest.raises((InsufficientFundsError, OverdraftLimitExceededError)):
        acc.withdraw(Decimal("101.00"))


# ── 13. Balance preserved after failed transaction ────────────────────────────


def test_balance_unchanged_after_failed_withdrawal(savings: SavingsAccount):
    before = savings.balance
    with pytest.raises(InsufficientFundsError):
        savings.withdraw(Decimal("9999.00"))
    assert savings.balance == before


def test_balance_unchanged_after_invalid_deposit(savings: SavingsAccount):
    before = savings.balance
    with pytest.raises(InvalidAmountError):
        savings.deposit(Decimal("-1"))
    assert savings.balance == before


# ── 11. Polymorphic processing ────────────────────────────────────────────────


def test_polymorphic_deposit_all_account_types():
    accounts: list[Account] = [
        SavingsAccount("S1", "INR", Decimal("100")),
        CheckingAccount("S2", "USD", Decimal("100")),
        HighYieldAccount("S3", "GBP", Decimal("100")),
    ]
    for acc in accounts:
        acc.deposit(Decimal("50.00"))
        assert acc.balance == Decimal("150.00")


# ── 16. Concurrent withdrawal safety ─────────────────────────────────────────


def test_concurrent_withdrawals_no_negative_balance():
    """50 threads each try to withdraw 10; total balance=100 so exactly
    10 should succeed and the rest must raise InsufficientFundsError.
    The final balance must be exactly 0 and never negative.
    """
    acc = SavingsAccount("Concurrent", "INR", Decimal("100.00"))
    successes = []
    failures = []
    lock = threading.Lock()

    def try_withdraw():
        try:
            acc.withdraw(Decimal("10.00"))
            with lock:
                successes.append(1)
        except InsufficientFundsError:
            with lock:
                failures.append(1)

    threads = [threading.Thread(target=try_withdraw) for _ in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(successes) == 10
    assert len(failures) == 40
    assert acc.balance == Decimal("0.00")


def test_concurrent_deposits_correct_final_balance():
    """100 threads each deposit 1; final balance must be exactly 100."""
    acc = SavingsAccount("DepositConc", "USD", Decimal("0"))
    threads = [
        threading.Thread(target=acc.deposit, args=(Decimal("1.00"),))
        for _ in range(100)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert acc.balance == Decimal("100.00")


# ── BankService creation and registry ────────────────────────────────────────


def test_bank_service_creates_and_registers_all_types():
    bank = BankService()
    s = bank.create_savings_account("Alice", "INR", Decimal("1000"))
    c = bank.create_checking_account("Bob", "USD", Decimal("500"))
    h = bank.create_high_yield_account("Carol", "GBP", Decimal("2000"))
    assert bank.account_count == 3
    assert bank.get_account(s.account_id) is s
    assert bank.get_account(c.account_id) is c
    assert bank.get_account(h.account_id) is h


def test_bank_service_invalid_config_not_registered():
    bank = BankService()
    with pytest.raises(AccountConfigurationError):
        bank.create_savings_account("X", "INR", Decimal("0"),
                                    interest_rate=Decimal("-1"))
    assert bank.account_count == 0
