"""
Immutable data models for the banking ledger engine.

Design notes
------------
* ``LedgerEntry`` is a *frozen* dataclass.  Once created it cannot be mutated
  by any caller, internal or external.  This is enforced by the Python
  dataclass machinery (``__setattr__`` / ``__delattr__`` raise
  ``FrozenInstanceError``).
* ``FeeCollectionResult`` carries the outcome of a ``deduct_fees()`` call.
  It is **not** a ledger entry and must never be appended to the financial
  ledger.  Operational events (e.g. a skipped fee) live here and nowhere
  else.
* All monetary fields use ``decimal.Decimal``; callers must not supply
  ``float`` values.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum


# ── Transaction type ──────────────────────────────────────────────────────────


class TransactionType(str, Enum):
    """Enumerated set of valid financial transaction types.

    Inheriting from ``str`` makes JSON serialisation straightforward while
    keeping enum identity comparisons intact.
    """

    DEPOSIT = "DEPOSIT"
    WITHDRAWAL = "WITHDRAWAL"
    INTEREST_CREDIT = "INTEREST_CREDIT"
    FEE_DEDUCTION = "FEE_DEDUCTION"
    OPENING_BALANCE = "OPENING_BALANCE"


# ── Financial ledger entry ────────────────────────────────────────────────────


@dataclass(frozen=True)
class LedgerEntry:
    """A single, immutable record in the financial ledger.

    Attributes
    ----------
    transaction_id:
        UUID-based unique identifier for the transaction.
    account_id:
        UUID of the account this entry belongs to.
    transaction_type:
        One of the :class:`TransactionType` values.
    amount:
        Positive ``Decimal`` amount of the transaction (always the absolute
        value of the change, never negative).
    currency:
        ISO 4217 currency code (e.g. ``"INR"``).
    balance_before:
        Account balance immediately *before* the transaction was applied.
    balance_after:
        Account balance immediately *after* the transaction was applied.
    timestamp:
        UTC datetime at which the transaction was committed.
    description:
        Human-readable reference or note (may be empty).
    """

    transaction_id: str
    account_id: str
    transaction_type: TransactionType
    amount: Decimal
    currency: str
    balance_before: Decimal
    balance_after: Decimal
    timestamp: datetime
    description: str = ""


# ── Operational result (never a ledger entry) ─────────────────────────────────


@dataclass(frozen=True)
class FeeCollectionResult:
    """Outcome of a ``deduct_fees()`` call.

    This is an *operational* result, not a financial transaction.  When
    ``success`` is ``False`` the fee was **not** collected and the account
    balance is **unchanged**.  No ledger entry is created for a failed fee
    collection.

    Attributes
    ----------
    success:
        ``True`` if the fee was collected (or if there was no fee to collect).
    amount:
        The fee amount that was attempted.  ``Decimal("0")`` when no fee
        applies.
    reason:
        Human-readable explanation.  Always populated when ``success`` is
        ``False``; may describe the no-fee case when ``success`` is ``True``.
    """

    success: bool
    amount: Decimal
    reason: str = ""


# ── Statement summary ─────────────────────────────────────────────────────────


@dataclass
class AccountSummary:
    """Aggregated totals derived from a set of ledger entries.

    Attributes
    ----------
    total_deposits:
        Sum of all DEPOSIT transaction amounts.
    total_withdrawals:
        Sum of all WITHDRAWAL transaction amounts.
    total_interest:
        Sum of all INTEREST_CREDIT transaction amounts.
    total_fees:
        Sum of all FEE_DEDUCTION transaction amounts.
    entry_count:
        Number of entries included in this summary.
    """

    total_deposits: Decimal
    total_withdrawals: Decimal
    total_interest: Decimal
    total_fees: Decimal
    entry_count: int
