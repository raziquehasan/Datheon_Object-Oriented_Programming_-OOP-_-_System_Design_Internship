"""
Account statement generation, filtering, summary calculation, and export.

All methods in this module work exclusively with the public account API and
immutable :class:`~banking.models.LedgerEntry` objects.  No private account
state is accessed.
"""

from __future__ import annotations

import csv
import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional, Tuple

from .accounts import Account
from .models import AccountSummary, LedgerEntry, TransactionType


# ── Transaction filter ────────────────────────────────────────────────────────


class TransactionFilter:
    """Static methods for filtering tuples of :class:`~banking.models.LedgerEntry`."""

    @staticmethod
    def by_type(
        entries: Tuple[LedgerEntry, ...],
        transaction_type: TransactionType,
    ) -> Tuple[LedgerEntry, ...]:
        """Return entries whose ``transaction_type`` matches *transaction_type*."""
        return tuple(e for e in entries if e.transaction_type == transaction_type)

    @staticmethod
    def by_date_range(
        entries: Tuple[LedgerEntry, ...],
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> Tuple[LedgerEntry, ...]:
        """Return entries within the inclusive datetime range [*start*, *end*].

        Parameters
        ----------
        entries:
            Source sequence of ledger entries.
        start:
            Inclusive lower bound (UTC).  ``None`` means no lower bound.
        end:
            Inclusive upper bound (UTC).  ``None`` means no upper bound.
        """
        result = entries
        if start is not None:
            result = tuple(e for e in result if e.timestamp >= start)
        if end is not None:
            result = tuple(e for e in result if e.timestamp <= end)
        return result


# ── Summary calculator ────────────────────────────────────────────────────────


class SummaryCalculator:
    """Computes aggregate totals from a tuple of ledger entries."""

    @staticmethod
    def calculate(entries: Tuple[LedgerEntry, ...]) -> AccountSummary:
        """Return an :class:`~banking.models.AccountSummary` for *entries*.

        Parameters
        ----------
        entries:
            Any sequence of :class:`~banking.models.LedgerEntry` objects.

        Returns
        -------
        AccountSummary
            Totals for deposits, withdrawals, interest credits, and fees.
        """
        zero = Decimal("0")

        total_deposits = sum(
            (e.amount for e in entries if e.transaction_type == TransactionType.DEPOSIT),
            zero,
        )
        total_withdrawals = sum(
            (e.amount for e in entries if e.transaction_type == TransactionType.WITHDRAWAL),
            zero,
        )
        total_interest = sum(
            (e.amount for e in entries if e.transaction_type == TransactionType.INTEREST_CREDIT),
            zero,
        )
        total_fees = sum(
            (e.amount for e in entries if e.transaction_type == TransactionType.FEE_DEDUCTION),
            zero,
        )
        return AccountSummary(
            total_deposits=total_deposits,
            total_withdrawals=total_withdrawals,
            total_interest=total_interest,
            total_fees=total_fees,
            entry_count=len(entries),
        )


# ── Statement exporter ────────────────────────────────────────────────────────


class StatementExporter:
    """Export account statements to JSON or CSV files.

    All ``Decimal`` values are serialised as strings to preserve precision.
    Parent directories are created automatically.
    """

    _CSV_FIELDS = [
        "transaction_id",
        "account_id",
        "type",
        "amount",
        "currency",
        "balance_before",
        "balance_after",
        "timestamp",
        "description",
    ]

    @staticmethod
    def to_json(account: Account, filepath: str) -> Path:
        """Write a full account statement to a JSON file.

        Parameters
        ----------
        account:
            The account to generate the statement for.
        filepath:
            Destination file path (created if it does not exist).

        Returns
        -------
        Path
            Resolved path to the written file.
        """
        statement = account.get_statement()
        path = Path(filepath).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(statement, fh, indent=2, default=str)
        return path

    @staticmethod
    def to_csv(account: Account, filepath: str) -> Path:
        """Write ledger entries to a CSV file.

        Parameters
        ----------
        account:
            The account whose ledger entries will be exported.
        filepath:
            Destination file path (created if it does not exist).

        Returns
        -------
        Path
            Resolved path to the written file.
        """
        entries = account.get_ledger_entries()
        path = Path(filepath).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=StatementExporter._CSV_FIELDS)
            writer.writeheader()
            for e in entries:
                writer.writerow(
                    {
                        "transaction_id": e.transaction_id,
                        "account_id": e.account_id,
                        "type": e.transaction_type.value,
                        "amount": str(e.amount),
                        "currency": e.currency,
                        "balance_before": str(e.balance_before),
                        "balance_after": str(e.balance_after),
                        "timestamp": e.timestamp.isoformat(),
                        "description": e.description,
                    }
                )
        return path
