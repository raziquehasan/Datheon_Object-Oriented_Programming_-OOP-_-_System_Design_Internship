"""
Thread-safe, append-only financial ledger.

Design notes
------------
* ``Ledger`` is the single store for :class:`~banking.models.LedgerEntry`
  objects.  Entries are appended by the account's atomic-commit method and
  never removed or modified.
* The ledger exposes entries only as **immutable tuples** (or individual
  frozen dataclass instances).  Callers cannot mutate the internal list.
* A single ``threading.RLock`` serialises all reads and writes to the
  entry list.  Because :class:`~banking.accounts.Account` holds *its own*
  lock during ``_commit()`` and the ledger append is the *last* step, the
  two-lock ordering is always account-lock → ledger-lock, which prevents
  deadlocks.
* The ``Ledger`` raises ``TypeError`` if a non-:class:`~banking.models.LedgerEntry`
  object is appended, providing a defence-in-depth check.
"""

from __future__ import annotations

import threading
from datetime import datetime
from typing import Optional, Tuple

from .models import LedgerEntry, TransactionType


class Ledger:
    """Append-only, thread-safe store for :class:`~banking.models.LedgerEntry` records.

    Each :class:`~banking.accounts.Account` instance creates exactly one
    ``Ledger`` during construction.  The ``Ledger`` is private to the account;
    callers only receive copies of entries through the account's public API.

    Methods
    -------
    append(entry):
        Add a validated entry.  Called by the account's atomic-commit path.
    get_entries(account_id, ...):
        Return a filtered, immutable tuple of entries.
    entry_count(account_id):
        Return the number of entries for an account.
    """

    def __init__(self) -> None:
        self._entries: list[LedgerEntry] = []
        self._lock: threading.RLock = threading.RLock()

    # ── Write ─────────────────────────────────────────────────────────────────

    def append(self, entry: LedgerEntry) -> None:
        """Append *entry* to the ledger.

        Parameters
        ----------
        entry:
            A :class:`~banking.models.LedgerEntry` instance.

        Raises
        ------
        TypeError
            If *entry* is not a :class:`~banking.models.LedgerEntry`.
        """
        if not isinstance(entry, LedgerEntry):
            raise TypeError(
                f"Ledger.append expects a LedgerEntry, got {type(entry).__name__}."
            )
        with self._lock:
            self._entries.append(entry)

    # ── Read ──────────────────────────────────────────────────────────────────

    def get_entries(
        self,
        account_id: str,
        transaction_type: Optional[TransactionType] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> Tuple[LedgerEntry, ...]:
        """Return a filtered, immutable tuple of entries for *account_id*.

        Filtering is applied in order: account → type → start_time → end_time.
        All returned entries are frozen dataclasses; they cannot be modified
        by the caller.

        Parameters
        ----------
        account_id:
            ID of the account whose entries are requested.
        transaction_type:
            If provided, only entries with this type are returned.
        start_time:
            If provided, only entries with ``timestamp >= start_time`` are
            returned (UTC datetime).
        end_time:
            If provided, only entries with ``timestamp <= end_time`` are
            returned (UTC datetime).

        Returns
        -------
        tuple[LedgerEntry, ...]
            Immutable, chronologically ordered sequence of matching entries.
        """
        with self._lock:
            # Take a snapshot of the list under the lock.
            entries: list[LedgerEntry] = [
                e for e in self._entries if e.account_id == account_id
            ]

        # Apply optional filters outside the lock (entries are immutable).
        if transaction_type is not None:
            entries = [e for e in entries if e.transaction_type == transaction_type]
        if start_time is not None:
            entries = [e for e in entries if e.timestamp >= start_time]
        if end_time is not None:
            entries = [e for e in entries if e.timestamp <= end_time]

        return tuple(entries)

    def entry_count(self, account_id: str) -> int:
        """Return the total number of entries recorded for *account_id*."""
        with self._lock:
            return sum(1 for e in self._entries if e.account_id == account_id)
