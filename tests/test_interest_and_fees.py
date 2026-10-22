"""
Tests for interest accrual and fee deduction across all account types.

Covers requirements:
 8. Interest calculations for each account type
 9. Fee deductions for each account type
10. High-yield minimum-balance eligibility
19. Correct rounding of monetary amounts
20. Edge cases involving zero balances and fees
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

import pytest

from banking import (
    CheckingAccount,
    HighYieldAccount,
    SavingsAccount,
)
from banking.models import FeeCollectionResult, TransactionType


# ── 8. Interest calculations ──────────────────────────────────────────────────


class TestSavingsInterest:
    def test_interest_credited_correctly(self):
        acc = SavingsAccount("A", "INR", Decimal("1000.00"),
                             interest_rate=Decimal("0.10"))
        entry = acc.accrue_interest()
        # 1000 * 0.10 = 100.00
        assert entry is not None
        assert entry.amount == Decimal("100.00")
        assert acc.balance == Decimal("1100.00")

    def test_interest_entry_in_ledger(self):
        acc = SavingsAccount("B", "USD", Decimal("500.00"),
                             interest_rate=Decimal("0.05"))
        acc.accrue_interest()
        interest_entries = acc.get_ledger_entries(
            transaction_type=TransactionType.INTEREST_CREDIT
        )
        assert len(interest_entries) == 1

    def test_zero_balance_no_interest(self):
        acc = SavingsAccount("C", "EUR", Decimal("0"),
                             interest_rate=Decimal("0.05"))
        entry = acc.accrue_interest()
        assert entry is None
        assert acc.balance == Decimal("0")

    def test_zero_interest_rate_no_credit(self):
        acc = SavingsAccount("D", "GBP", Decimal("1000.00"),
                             interest_rate=Decimal("0"))
        entry = acc.accrue_interest()
        assert entry is None

    def test_savings_no_fee(self):
        acc = SavingsAccount("E", "INR", Decimal("100.00"))
        result = acc.deduct_fees()
        assert result.success is True
        assert result.amount == Decimal("0")

    def test_multiple_interest_accruals_compound(self):
        acc = SavingsAccount("F", "INR", Decimal("1000.00"),
                             interest_rate=Decimal("0.10"))
        acc.accrue_interest()  # balance → 1100
        acc.accrue_interest()  # balance → 1210
        assert acc.balance == Decimal("1210.00")


class TestCheckingInterest:
    def test_interest_credited(self):
        acc = CheckingAccount("G", "USD", Decimal("10000.00"),
                              interest_rate=Decimal("0.01"))
        entry = acc.accrue_interest()
        assert entry is not None
        assert entry.amount == Decimal("100.00")
        assert acc.balance == Decimal("10100.00")

    def test_zero_balance_no_interest(self):
        acc = CheckingAccount("H", "USD", Decimal("0"),
                              interest_rate=Decimal("0.05"))
        entry = acc.accrue_interest()
        assert entry is None

    def test_maintenance_fee_deducted(self):
        acc = CheckingAccount("I", "USD", Decimal("500.00"),
                              maintenance_fee=Decimal("12.50"))
        result = acc.deduct_fees()
        assert result.success is True
        assert result.amount == Decimal("12.50")
        assert acc.balance == Decimal("487.50")

    def test_fee_in_ledger(self):
        acc = CheckingAccount("J", "USD", Decimal("200.00"),
                              maintenance_fee=Decimal("20.00"))
        acc.deduct_fees()
        fee_entries = acc.get_ledger_entries(
            transaction_type=TransactionType.FEE_DEDUCTION
        )
        assert len(fee_entries) == 1
        assert fee_entries[0].amount == Decimal("20.00")

    def test_fee_skipped_insufficient_balance(self):
        """Fee cannot be collected → balance unchanged, no ledger entry."""
        acc = CheckingAccount("K", "USD", Decimal("5.00"),
                              maintenance_fee=Decimal("10.00"))
        before = acc.balance
        ledger_before = len(acc.get_ledger_entries())
        result = acc.deduct_fees()
        assert result.success is False
        assert acc.balance == before  # unchanged
        assert len(acc.get_ledger_entries()) == ledger_before  # no new entry

    def test_zero_fee_no_deduction(self):
        acc = CheckingAccount("L", "USD", Decimal("100.00"),
                              maintenance_fee=Decimal("0"))
        result = acc.deduct_fees()
        assert result.success is True
        assert result.amount == Decimal("0")
        assert acc.balance == Decimal("100.00")


class TestHighYieldInterest:
    def test_interest_when_eligible(self):
        acc = HighYieldAccount("M", "GBP", Decimal("2000.00"),
                               interest_rate=Decimal("0.07"),
                               minimum_balance=Decimal("1000.00"))
        entry = acc.accrue_interest()
        # 2000 * 0.07 = 140.00
        assert entry is not None
        assert entry.amount == Decimal("140.00")
        assert acc.balance == Decimal("2140.00")

    def test_no_interest_below_minimum(self):
        acc = HighYieldAccount("N", "GBP", Decimal("500.00"),
                               interest_rate=Decimal("0.07"),
                               minimum_balance=Decimal("1000.00"))
        entry = acc.accrue_interest()
        assert entry is None
        assert acc.balance == Decimal("500.00")

    def test_exactly_at_minimum_receives_interest(self):
        acc = HighYieldAccount("O", "GBP", Decimal("1000.00"),
                               interest_rate=Decimal("0.07"),
                               minimum_balance=Decimal("1000.00"))
        entry = acc.accrue_interest()
        assert entry is not None
        # 1000 * 0.07 = 70.00
        assert entry.amount == Decimal("70.00")


# ── 10. High-yield minimum-balance eligibility ───────────────────────────────


class TestHighYieldFees:
    def test_fee_charged_below_minimum(self):
        acc = HighYieldAccount("P", "GBP", Decimal("500.00"),
                               minimum_balance=Decimal("1000.00"),
                               below_minimum_fee=Decimal("20.00"))
        result = acc.deduct_fees()
        assert result.success is True
        assert result.amount == Decimal("20.00")
        assert acc.balance == Decimal("480.00")

    def test_no_fee_above_minimum(self):
        acc = HighYieldAccount("Q", "GBP", Decimal("2000.00"),
                               minimum_balance=Decimal("1000.00"),
                               below_minimum_fee=Decimal("20.00"))
        result = acc.deduct_fees()
        assert result.success is True
        assert result.amount == Decimal("0")
        assert acc.balance == Decimal("2000.00")

    def test_fee_skipped_if_balance_too_low_to_pay_it(self):
        """Balance below min AND below fee → fee skipped, no ledger entry."""
        acc = HighYieldAccount("R", "GBP", Decimal("10.00"),
                               minimum_balance=Decimal("1000.00"),
                               below_minimum_fee=Decimal("20.00"))
        before = acc.balance
        before_count = len(acc.get_ledger_entries())
        result = acc.deduct_fees()
        assert result.success is False
        assert acc.balance == before
        assert len(acc.get_ledger_entries()) == before_count

    def test_is_eligible_for_interest_property(self):
        acc = HighYieldAccount("S", "GBP", Decimal("1500.00"),
                               minimum_balance=Decimal("1000.00"))
        assert acc.is_eligible_for_interest is True
        acc.withdraw(Decimal("600.00"))  # balance → 900
        assert acc.is_eligible_for_interest is False


# ── 19. Correct rounding of monetary amounts ──────────────────────────────────


class TestRounding:
    def test_interest_rounds_half_up(self):
        """1 / 3 * rate should round to correct decimal places."""
        # balance=3, rate=1/3 → 1.0 exactly? Use a tricky case.
        # balance=100, rate=0.333 → 33.3 → should round to 33.30
        acc = SavingsAccount("Round1", "USD", Decimal("100.00"),
                             interest_rate=Decimal("0.333"))
        entry = acc.accrue_interest()
        assert entry is not None
        # 100 * 0.333 = 33.3 → ROUND_HALF_UP → 33.30
        assert entry.amount == Decimal("33.30")

    def test_interest_round_half_up_midpoint(self):
        # 1000 * 0.0015 = 1.5 → ROUND_HALF_UP → 1.50
        acc = SavingsAccount("Round2", "USD", Decimal("1000.00"),
                             interest_rate=Decimal("0.0015"))
        entry = acc.accrue_interest()
        assert entry is not None
        assert entry.amount == Decimal("1.50")

    def test_all_ledger_amounts_have_correct_decimal_places(self):
        acc = SavingsAccount("Round3", "USD", Decimal("999.99"),
                             interest_rate=Decimal("0.035"))
        acc.deposit(Decimal("0.01"))
        acc.accrue_interest()
        for entry in acc.get_ledger_entries():
            # All USD amounts should have at most 2 decimal places
            assert entry.amount == entry.amount.quantize(Decimal("0.01"),
                                                         rounding=ROUND_HALF_UP)


# ── 20. Edge cases: zero balances and fees ────────────────────────────────────


class TestEdgeCases:
    def test_interest_on_penny_balance(self):
        # 0.01 * 0.035 = 0.00035 → rounds to 0.00 → no interest entry
        acc = SavingsAccount("Penny", "USD", Decimal("0.01"),
                             interest_rate=Decimal("0.035"))
        entry = acc.accrue_interest()
        # 0.01 * 0.035 = 0.00035 → rounds to 0.00 → no credit
        assert entry is None

    def test_fee_exactly_equals_balance(self):
        """Fee equals balance → fee collected, balance becomes 0."""
        acc = CheckingAccount("Zero", "USD", Decimal("10.00"),
                              maintenance_fee=Decimal("10.00"))
        result = acc.deduct_fees()
        assert result.success is True
        assert acc.balance == Decimal("0.00")

    def test_zero_balance_fee_skipped(self):
        acc = CheckingAccount("ZeroFee", "USD", Decimal("0"),
                              maintenance_fee=Decimal("10.00"))
        result = acc.deduct_fees()
        assert result.success is False
        assert acc.balance == Decimal("0")

    def test_fee_collection_result_is_not_ledger_entry(self):
        """Skipped fee must produce no ledger entry of any kind."""
        acc = CheckingAccount("NoEntry", "USD", Decimal("5.00"),
                              maintenance_fee=Decimal("10.00"))
        entries_before = acc.get_ledger_entries()
        result = acc.deduct_fees()
        entries_after = acc.get_ledger_entries()
        assert result.success is False
        # Ledger must be unchanged
        assert len(entries_after) == len(entries_before)
        # Verify no FEE_DEDUCTION entry exists
        fee_entries = acc.get_ledger_entries(
            transaction_type=TransactionType.FEE_DEDUCTION
        )
        assert len(fee_entries) == 0
