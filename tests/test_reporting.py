"""
Tests for statement generation and export.

Covers requirements:
17. Statement generation and export (JSON and CSV)
"""

from __future__ import annotations

import csv
import json
import tempfile
from decimal import Decimal
from pathlib import Path

import pytest

from banking import (
    SavingsAccount,
    CheckingAccount,
    StatementExporter,
    SummaryCalculator,
    TransactionFilter,
)
from banking.models import TransactionType


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def populated_savings() -> SavingsAccount:
    acc = SavingsAccount("Alice", "INR", Decimal("5000.00"),
                         interest_rate=Decimal("0.05"))
    acc.deposit(Decimal("1000.00"))
    acc.withdraw(Decimal("500.00"))
    acc.accrue_interest()
    acc.deduct_fees()  # savings has no fee; result is no-op
    return acc


@pytest.fixture
def populated_checking() -> CheckingAccount:
    acc = CheckingAccount("Bob", "USD", Decimal("1000.00"),
                          maintenance_fee=Decimal("15.00"))
    acc.deposit(Decimal("200.00"))
    acc.withdraw(Decimal("100.00"))
    acc.deduct_fees()
    return acc


# ── get_statement ─────────────────────────────────────────────────────────────


def test_statement_contains_required_keys(populated_savings: SavingsAccount):
    stmt = populated_savings.get_statement()
    for key in ["account_id", "account_type", "holder_name", "currency",
                "balance", "created_at", "generated_at", "entries"]:
        assert key in stmt


def test_statement_balance_as_string(populated_savings: SavingsAccount):
    stmt = populated_savings.get_statement()
    # Balance must be a string (Decimal serialised for precision)
    assert isinstance(stmt["balance"], str)
    # Must match actual balance
    assert Decimal(stmt["balance"]) == populated_savings.balance


def test_statement_entries_serialisable(populated_savings: SavingsAccount):
    stmt = populated_savings.get_statement()
    # Must be JSON-serialisable without a custom encoder
    serialised = json.dumps(stmt)
    parsed = json.loads(serialised)
    assert len(parsed["entries"]) == len(stmt["entries"])


def test_statement_does_not_expose_private_objects(populated_savings: SavingsAccount):
    """Statement entries should be dicts, not LedgerEntry objects."""
    stmt = populated_savings.get_statement()
    from banking.models import LedgerEntry
    for entry in stmt["entries"]:
        assert isinstance(entry, dict)
        assert not isinstance(entry, LedgerEntry)


def test_statement_entry_has_all_fields(populated_savings: SavingsAccount):
    stmt = populated_savings.get_statement()
    required = {"transaction_id", "type", "amount", "currency",
                "balance_before", "balance_after", "timestamp", "description"}
    for entry in stmt["entries"]:
        assert required.issubset(entry.keys())


# ── TransactionFilter ─────────────────────────────────────────────────────────


def test_filter_by_type_deposit(populated_savings: SavingsAccount):
    entries = populated_savings.get_ledger_entries()
    deposits = TransactionFilter.by_type(entries, TransactionType.DEPOSIT)
    assert all(e.transaction_type == TransactionType.DEPOSIT for e in deposits)
    assert len(deposits) == 1


def test_filter_by_type_withdrawal(populated_savings: SavingsAccount):
    entries = populated_savings.get_ledger_entries()
    withdrawals = TransactionFilter.by_type(entries, TransactionType.WITHDRAWAL)
    assert len(withdrawals) == 1


def test_filter_by_date_range_all(populated_savings: SavingsAccount):
    from datetime import datetime, timezone, timedelta
    entries = populated_savings.get_ledger_entries()
    far_past = datetime(2000, 1, 1, tzinfo=timezone.utc)
    far_future = datetime(2100, 1, 1, tzinfo=timezone.utc)
    filtered = TransactionFilter.by_date_range(entries, far_past, far_future)
    assert len(filtered) == len(entries)


def test_filter_by_date_range_empty(populated_savings: SavingsAccount):
    from datetime import datetime, timezone
    entries = populated_savings.get_ledger_entries()
    far_future = datetime(2100, 1, 1, tzinfo=timezone.utc)
    filtered = TransactionFilter.by_date_range(entries, start=far_future)
    assert len(filtered) == 0


# ── SummaryCalculator ─────────────────────────────────────────────────────────


def test_summary_totals(populated_savings: SavingsAccount):
    entries = populated_savings.get_ledger_entries()
    summary = SummaryCalculator.calculate(entries)
    assert summary.total_deposits == Decimal("1000.00")
    assert summary.total_withdrawals == Decimal("500.00")
    assert summary.total_interest > Decimal("0")
    assert summary.total_fees == Decimal("0")


def test_summary_entry_count(populated_savings: SavingsAccount):
    entries = populated_savings.get_ledger_entries()
    summary = SummaryCalculator.calculate(entries)
    assert summary.entry_count == len(entries)


def test_summary_checking_includes_fee(populated_checking: CheckingAccount):
    entries = populated_checking.get_ledger_entries()
    summary = SummaryCalculator.calculate(entries)
    assert summary.total_fees == Decimal("15.00")
    assert summary.total_deposits == Decimal("200.00")
    assert summary.total_withdrawals == Decimal("100.00")


def test_summary_empty_entries():
    summary = SummaryCalculator.calculate(())
    assert summary.total_deposits == Decimal("0")
    assert summary.entry_count == 0


# ── StatementExporter — JSON ──────────────────────────────────────────────────


def test_export_to_json_creates_file(populated_savings: SavingsAccount):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "statement.json"
        result = StatementExporter.to_json(populated_savings, str(path))
        assert result.exists()


def test_export_to_json_valid_content(populated_savings: SavingsAccount):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "stmt.json"
        StatementExporter.to_json(populated_savings, str(path))
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        assert data["account_id"] == populated_savings.account_id
        assert data["holder_name"] == "Alice"
        assert len(data["entries"]) > 0


def test_export_to_json_amounts_are_strings(populated_savings: SavingsAccount):
    """Amounts in JSON export must be strings (not floats) for precision."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "amounts.json"
        StatementExporter.to_json(populated_savings, str(path))
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        for entry in data["entries"]:
            assert isinstance(entry["amount"], str)


# ── StatementExporter — CSV ────────────────────────────────────────────────────


def test_export_to_csv_creates_file(populated_savings: SavingsAccount):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "statement.csv"
        result = StatementExporter.to_csv(populated_savings, str(path))
        assert result.exists()


def test_export_to_csv_correct_rows(populated_savings: SavingsAccount):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "rows.csv"
        StatementExporter.to_csv(populated_savings, str(path))
        with open(path, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            rows = list(reader)
        expected_count = len(populated_savings.get_ledger_entries())
        assert len(rows) == expected_count


def test_export_to_csv_has_required_columns(populated_savings: SavingsAccount):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "cols.csv"
        StatementExporter.to_csv(populated_savings, str(path))
        with open(path, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            rows = list(reader)
        required = {"transaction_id", "account_id", "type", "amount",
                    "currency", "balance_before", "balance_after",
                    "timestamp", "description"}
        assert required.issubset(rows[0].keys())


def test_export_creates_parent_directories(populated_savings: SavingsAccount):
    with tempfile.TemporaryDirectory() as tmp:
        nested = Path(tmp) / "a" / "b" / "c" / "output.json"
        StatementExporter.to_json(populated_savings, str(nested))
        assert nested.exists()
