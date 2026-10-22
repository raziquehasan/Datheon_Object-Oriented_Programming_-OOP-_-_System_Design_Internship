"""
Account hierarchy: abstract base + three concrete account types.

OOP pillars demonstrated
------------------------
Abstraction
    ``Account`` is an abstract base class (``abc.ABC``).  ``accrue_interest``
    and ``deduct_fees`` are abstract methods; any concrete subclass *must*
    implement them.

Encapsulation
    All sensitive state (``_balance``, ``_id``, ``_ledger``) is private.
    Balances are exposed only through read-only properties.  The internal
    ledger list is never handed to callers; they receive only immutable tuples.

Inheritance
    ``SavingsAccount``, ``CheckingAccount``, and ``HighYieldAccount`` all
    inherit from ``Account`` and reuse its ``deposit``, ``withdraw``, and
    ``_commit`` logic.

Polymorphism
    The ``_check_withdrawal`` and ``accrue_interest`` / ``deduct_fees``
    methods have different implementations per subclass.  Client code
    (e.g. ``BankService.process_interest_and_fees``) calls these through the
    common ``Account`` interface without inspecting the concrete type.

Atomicity guarantee
-------------------
Every mutation goes through ``_commit()``, which:

1. Constructs the ``LedgerEntry`` (no side effects).
2. Saves the current balance.
3. Updates ``self._balance`` to the new value.
4. Attempts to append the entry to the ledger.
5. If the ledger append raises, ``self._balance`` is restored to the saved
   value *before* the exception propagates.

Steps 2-5 execute while ``self._lock`` is held, so no other thread can
observe an intermediate state.

Fee-collection policy
---------------------
When a fee cannot be collected (e.g. insufficient funds), the balance is
*not* changed and *no* ledger entry is created.  The outcome is reported
solely through the returned :class:`~banking.models.FeeCollectionResult`.
Operational events (skipped fees) are the caller's responsibility to log.
"""

from __future__ import annotations

import threading
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from .currency import validate_currency, validate_amount, round_for_currency
from .exceptions import (
    AccountConfigurationError,
    AtomicOperationError,
    InsufficientFundsError,
    InvalidAccountError,
    InvalidAmountError,
    OverdraftLimitExceededError,
)
from .ledger import Ledger
from .models import FeeCollectionResult, LedgerEntry, TransactionType


# ── Abstract base ─────────────────────────────────────────────────────────────


class Account(ABC):
    """Abstract base class for all bank accounts.

    Subclasses **must** implement:

    * :meth:`accrue_interest` — apply interest for one period.
    * :meth:`deduct_fees` — apply account fees for one period.

    All monetary arguments must be ``decimal.Decimal``.

    Parameters
    ----------
    holder_name:
        Non-empty account holder name.
    currency:
        ISO 4217 currency code; must be in
        :data:`~banking.currency.SUPPORTED_CURRENCIES`.
    initial_balance:
        Non-negative opening balance (default ``Decimal("0")``).
    ledger:
        Optional shared :class:`~banking.ledger.Ledger` instance.  If
        ``None`` (the default), a private ledger is created.
    """

    def __init__(
        self,
        holder_name: str,
        currency: str,
        initial_balance: Decimal = Decimal("0"),
        ledger: Optional[Ledger] = None,
    ) -> None:
        # ── Validate before any state is created ──────────────────────────────
        if not isinstance(holder_name, str) or not holder_name.strip():
            raise InvalidAccountError(
                "Account holder name must be a non-empty string."
            )
        validate_currency(currency)
        if not isinstance(initial_balance, Decimal):
            raise InvalidAmountError(
                f"initial_balance must be Decimal, got {type(initial_balance).__name__}."
            )
        if not initial_balance.is_finite():
            raise InvalidAmountError(
                "initial_balance must be a finite number (no NaN or Infinity)."
            )
        if initial_balance < Decimal("0"):
            raise InvalidAmountError(
                "initial_balance cannot be negative."
            )

        # ── Initialise private state ───────────────────────────────────────────
        self._id: str = str(uuid.uuid4())
        self._holder_name: str = holder_name.strip()
        self._currency: str = currency
        self._balance: Decimal = round_for_currency(initial_balance, currency)
        self._created_at: datetime = datetime.now(timezone.utc)
        self._lock: threading.RLock = threading.RLock()
        self._ledger: Ledger = ledger if ledger is not None else Ledger()

        # Record the opening balance in the ledger if non-zero.
        if self._balance > Decimal("0"):
            opening_entry = LedgerEntry(
                transaction_id=str(uuid.uuid4()),
                account_id=self._id,
                transaction_type=TransactionType.OPENING_BALANCE,
                amount=self._balance,
                currency=self._currency,
                balance_before=Decimal("0"),
                balance_after=self._balance,
                timestamp=self._created_at,
                description="Account opened with initial balance.",
            )
            self._ledger.append(opening_entry)

    # ── Read-only properties ──────────────────────────────────────────────────

    @property
    def account_id(self) -> str:
        """Unique, immutable account identifier (UUID string)."""
        return self._id

    @property
    def holder_name(self) -> str:
        """Account holder's name (stripped of leading/trailing whitespace)."""
        return self._holder_name

    @property
    def currency(self) -> str:
        """ISO 4217 currency code for this account."""
        return self._currency

    @property
    def balance(self) -> Decimal:
        """Current account balance (thread-safe snapshot)."""
        with self._lock:
            return self._balance

    @property
    def created_at(self) -> datetime:
        """UTC datetime at which the account was created."""
        return self._created_at

    # ── Abstract interface ────────────────────────────────────────────────────

    @abstractmethod
    def accrue_interest(self) -> Optional[LedgerEntry]:
        """Apply one period of interest to this account.

        Returns
        -------
        LedgerEntry or None
            The ledger entry for the interest credit, or ``None`` if no
            interest was applicable (e.g. zero balance, eligibility not met).
        """

    @abstractmethod
    def deduct_fees(self) -> FeeCollectionResult:
        """Apply one period of fees to this account.

        Returns
        -------
        FeeCollectionResult
            ``success=True`` if the fee was collected (or if no fee applies).
            ``success=False`` if the fee could not be collected; in this case
            the balance is **unchanged** and **no ledger entry is created**.
        """

    # ── Concrete public operations ────────────────────────────────────────────

    def deposit(self, amount: Decimal, description: str = "") -> LedgerEntry:
        """Deposit *amount* into this account.

        Parameters
        ----------
        amount:
            Positive, finite ``Decimal`` in this account's currency.
        description:
            Optional human-readable reference.

        Returns
        -------
        LedgerEntry
            The immutable ledger record for this deposit.

        Raises
        ------
        InvalidAmountError
            If *amount* is invalid.
        """
        validated = validate_amount(amount, self._currency)
        with self._lock:
            return self._commit(
                amount=validated,
                new_balance=self._balance + validated,
                transaction_type=TransactionType.DEPOSIT,
                description=description or "Deposit",
            )

    def withdraw(self, amount: Decimal, description: str = "") -> LedgerEntry:
        """Withdraw *amount* from this account.

        Subclasses override :meth:`_check_withdrawal` to apply their own
        balance / overdraft rules.

        Parameters
        ----------
        amount:
            Positive, finite ``Decimal`` in this account's currency.
        description:
            Optional human-readable reference.

        Returns
        -------
        LedgerEntry
            The immutable ledger record for this withdrawal.

        Raises
        ------
        InvalidAmountError
            If *amount* is invalid.
        InsufficientFundsError
            If the withdrawal would violate the account's balance policy.
        """
        validated = validate_amount(amount, self._currency)
        with self._lock:
            self._check_withdrawal(validated)
            return self._commit(
                amount=validated,
                new_balance=self._balance - validated,
                transaction_type=TransactionType.WITHDRAWAL,
                description=description or "Withdrawal",
            )

    def get_ledger_entries(
        self,
        transaction_type: Optional[TransactionType] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> tuple[LedgerEntry, ...]:
        """Return an immutable, optionally filtered tuple of ledger entries.

        Parameters
        ----------
        transaction_type:
            Filter by :class:`~banking.models.TransactionType`.
        start_time:
            Inclusive lower bound (UTC).
        end_time:
            Inclusive upper bound (UTC).

        Returns
        -------
        tuple[LedgerEntry, ...]
            Chronologically ordered, immutable entries.
        """
        return self._ledger.get_entries(
            self._id,
            transaction_type=transaction_type,
            start_time=start_time,
            end_time=end_time,
        )

    def get_statement(self) -> dict:
        """Return a serialisable account statement dictionary.

        The returned dict contains no references to internal mutable objects.
        All ``Decimal`` values are represented as strings to preserve precision
        across serialisation boundaries.

        Returns
        -------
        dict
            Account metadata plus a list of ledger entry dicts.
        """
        entries = self._ledger.get_entries(self._id)
        return {
            "account_id": self._id,
            "account_type": type(self).__name__,
            "holder_name": self._holder_name,
            "currency": self._currency,
            "balance": str(self._balance),
            "created_at": self._created_at.isoformat(),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "entries": [
                {
                    "transaction_id": e.transaction_id,
                    "type": e.transaction_type.value,
                    "amount": str(e.amount),
                    "currency": e.currency,
                    "balance_before": str(e.balance_before),
                    "balance_after": str(e.balance_after),
                    "timestamp": e.timestamp.isoformat(),
                    "description": e.description,
                }
                for e in entries
            ],
        }

    # ── Protected helpers ─────────────────────────────────────────────────────

    def _check_withdrawal(self, amount: Decimal) -> None:
        """Enforce the account's withdrawal / overdraft policy.

        Called by :meth:`withdraw` *while* ``self._lock`` is held.
        Override in subclasses to implement custom rules.

        Raises
        ------
        InsufficientFundsError
            Default: raises if *amount* > current balance.
        """
        if amount > self._balance:
            raise InsufficientFundsError(
                f"Insufficient funds.  Balance: {self._balance} {self._currency}, "
                f"Requested: {amount} {self._currency}."
            )

    def _commit(
        self,
        amount: Decimal,
        new_balance: Decimal,
        transaction_type: TransactionType,
        description: str,
    ) -> LedgerEntry:
        """Atomically update the balance and append a ledger entry.

        This method **must** be called while ``self._lock`` is held.  It
        guarantees that the balance and the ledger entry are *always*
        consistent:

        1. The :class:`~banking.models.LedgerEntry` is constructed (pure
           computation — no side effects).
        2. The old balance is captured.
        3. ``self._balance`` is set to *new_balance*.
        4. The entry is appended to the ledger.
        5. If step 4 raises (e.g. in tests that inject a failing ledger),
           ``self._balance`` is restored to its step-2 value and
           :class:`~banking.exceptions.AtomicOperationError` is raised.

        Parameters
        ----------
        amount:
            Positive ``Decimal`` magnitude of the change.
        new_balance:
            Pre-computed balance after the operation.
        transaction_type:
            One of the :class:`~banking.models.TransactionType` values.
        description:
            Human-readable transaction reference.

        Returns
        -------
        LedgerEntry
            The frozen ledger entry that was committed.

        Raises
        ------
        AtomicOperationError
            If the ledger append fails; balance is rolled back.
        """
        entry = LedgerEntry(
            transaction_id=str(uuid.uuid4()),
            account_id=self._id,
            transaction_type=transaction_type,
            amount=amount,
            currency=self._currency,
            balance_before=self._balance,
            balance_after=new_balance,
            timestamp=datetime.now(timezone.utc),
            description=description,
        )

        old_balance = self._balance
        self._balance = new_balance
        try:
            self._ledger.append(entry)
        except Exception as exc:
            # Roll back: the caller must never see an updated balance without
            # a matching ledger entry.
            self._balance = old_balance
            raise AtomicOperationError(
                f"Ledger append failed; balance rolled back to {old_balance}.  "
                f"Cause: {exc}"
            ) from exc

        return entry


# ── SavingsAccount ────────────────────────────────────────────────────────────


class SavingsAccount(Account):
    """Savings account that earns configurable interest and prohibits overdrafts.

    Interest policy
    ---------------
    Simple interest computed as ``balance × interest_rate`` per period.
    Rounded to the currency's decimal precision using ``ROUND_HALF_UP``.
    No interest is credited if the balance is zero.

    Fee policy
    ----------
    No maintenance fee.  :meth:`deduct_fees` always returns a successful
    zero-amount result.

    Withdrawal policy
    -----------------
    Withdrawals are rejected if they would reduce the balance below zero
    (no overdraft).

    Parameters
    ----------
    holder_name:
        Non-empty account holder name.
    currency:
        ISO 4217 currency code.
    initial_balance:
        Non-negative opening balance (default ``Decimal("0")``).
    interest_rate:
        Non-negative annual interest rate as a proportion (e.g.
        ``Decimal("0.035")`` for 3.5 %).  Default: 3.5 %.
    ledger:
        Optional shared ledger instance.

    Notes
    -----
    The default interest rate (3.5 %) is a demonstration value only and
    does not represent any real bank product or financial advice.
    """

    DEFAULT_INTEREST_RATE: Decimal = Decimal("0.035")

    def __init__(
        self,
        holder_name: str,
        currency: str,
        initial_balance: Decimal = Decimal("0"),
        interest_rate: Decimal = DEFAULT_INTEREST_RATE,
        ledger: Optional[Ledger] = None,
    ) -> None:
        if not isinstance(interest_rate, Decimal):
            raise AccountConfigurationError(
                f"interest_rate must be Decimal, got {type(interest_rate).__name__}."
            )
        if not interest_rate.is_finite() or interest_rate < Decimal("0"):
            raise AccountConfigurationError(
                f"interest_rate must be a non-negative finite Decimal, got {interest_rate!s}."
            )
        super().__init__(holder_name, currency, initial_balance, ledger)
        self._interest_rate: Decimal = interest_rate

    @property
    def interest_rate(self) -> Decimal:
        """Annual interest rate as a proportion (read-only)."""
        return self._interest_rate

    # ── Abstract implementations ──────────────────────────────────────────────

    def accrue_interest(self) -> Optional[LedgerEntry]:
        """Credit simple interest for one period.

        Returns ``None`` if the current balance is zero (no interest to credit).
        """
        with self._lock:
            if self._balance <= Decimal("0"):
                return None
            interest = round_for_currency(
                self._balance * self._interest_rate, self._currency
            )
            if interest <= Decimal("0"):
                return None
            return self._commit(
                amount=interest,
                new_balance=self._balance + interest,
                transaction_type=TransactionType.INTEREST_CREDIT,
                description=(
                    f"Interest accrual at "
                    f"{self._interest_rate * 100:.4f}% per period."
                ),
            )

    def deduct_fees(self) -> FeeCollectionResult:
        """No fee applies to SavingsAccount.

        Always returns ``FeeCollectionResult(success=True, amount=Decimal("0"))``.
        """
        return FeeCollectionResult(
            success=True,
            amount=Decimal("0"),
            reason="SavingsAccount has no maintenance fee.",
        )

    # ── Override withdrawal check ─────────────────────────────────────────────

    def _check_withdrawal(self, amount: Decimal) -> None:
        """Reject withdrawals that would overdraft the account."""
        if amount > self._balance:
            raise InsufficientFundsError(
                f"SavingsAccount does not permit overdraft.  "
                f"Balance: {self._balance} {self._currency}, "
                f"Requested: {amount} {self._currency}."
            )


# ── CheckingAccount ───────────────────────────────────────────────────────────


class CheckingAccount(Account):
    """Checking account with optional overdraft and a monthly maintenance fee.

    Interest policy
    ---------------
    Simple interest at a low configurable rate, credited per period.
    No interest is credited on negative balances.

    Fee policy
    ----------
    A configurable monthly maintenance fee is deducted from the balance.
    If the balance is insufficient to cover the fee *at the time of
    collection*, the fee is **skipped** (the balance is not modified and no
    ledger entry is created).  The caller receives a
    :class:`~banking.models.FeeCollectionResult` with ``success=False``.

    Withdrawal policy
    -----------------
    Withdrawals may exceed the balance up to the configured ``overdraft_limit``.
    Withdrawals beyond ``balance + overdraft_limit`` are rejected.

    Parameters
    ----------
    holder_name:
        Non-empty account holder name.
    currency:
        ISO 4217 currency code.
    initial_balance:
        Non-negative opening balance (default ``Decimal("0")``).
    maintenance_fee:
        Non-negative monthly fee (default 10.00 in account currency).
    overdraft_limit:
        Non-negative overdraft allowance (default ``Decimal("0")``).
    interest_rate:
        Non-negative annual interest rate as a proportion (default 0.1 %).
    ledger:
        Optional shared ledger instance.

    Notes
    -----
    Default values are demonstration values only.
    """

    DEFAULT_MAINTENANCE_FEE: Decimal = Decimal("10.00")
    DEFAULT_INTEREST_RATE: Decimal = Decimal("0.001")

    def __init__(
        self,
        holder_name: str,
        currency: str,
        initial_balance: Decimal = Decimal("0"),
        maintenance_fee: Decimal = DEFAULT_MAINTENANCE_FEE,
        overdraft_limit: Decimal = Decimal("0"),
        interest_rate: Decimal = DEFAULT_INTEREST_RATE,
        ledger: Optional[Ledger] = None,
    ) -> None:
        for name, val in [
            ("maintenance_fee", maintenance_fee),
            ("overdraft_limit", overdraft_limit),
            ("interest_rate", interest_rate),
        ]:
            if not isinstance(val, Decimal):
                raise AccountConfigurationError(
                    f"{name} must be Decimal, got {type(val).__name__}."
                )
            if not val.is_finite() or val < Decimal("0"):
                raise AccountConfigurationError(
                    f"{name} must be a non-negative finite Decimal, got {val!s}."
                )

        super().__init__(holder_name, currency, initial_balance, ledger)
        self._maintenance_fee: Decimal = maintenance_fee
        self._overdraft_limit: Decimal = overdraft_limit
        self._interest_rate: Decimal = interest_rate

    @property
    def maintenance_fee(self) -> Decimal:
        """Configured monthly maintenance fee (read-only)."""
        return self._maintenance_fee

    @property
    def overdraft_limit(self) -> Decimal:
        """Configured overdraft limit (read-only)."""
        return self._overdraft_limit

    @property
    def interest_rate(self) -> Decimal:
        """Annual interest rate as a proportion (read-only)."""
        return self._interest_rate

    # ── Abstract implementations ──────────────────────────────────────────────

    def accrue_interest(self) -> Optional[LedgerEntry]:
        """Credit simple interest for one period.

        Returns ``None`` if the balance is zero or negative.
        """
        with self._lock:
            if self._balance <= Decimal("0"):
                return None
            interest = round_for_currency(
                self._balance * self._interest_rate, self._currency
            )
            if interest <= Decimal("0"):
                return None
            return self._commit(
                amount=interest,
                new_balance=self._balance + interest,
                transaction_type=TransactionType.INTEREST_CREDIT,
                description=(
                    f"Interest accrual at "
                    f"{self._interest_rate * 100:.4f}% per period."
                ),
            )

    def deduct_fees(self) -> FeeCollectionResult:
        """Deduct the monthly maintenance fee.

        If ``maintenance_fee`` is zero, returns success with zero amount.
        If the balance is insufficient, the fee is **skipped** (balance
        unchanged, no ledger entry).

        Returns
        -------
        FeeCollectionResult
            Outcome of the fee collection attempt.
        """
        with self._lock:
            if self._maintenance_fee <= Decimal("0"):
                return FeeCollectionResult(
                    success=True,
                    amount=Decimal("0"),
                    reason="No maintenance fee configured.",
                )
            if self._balance < self._maintenance_fee:
                return FeeCollectionResult(
                    success=False,
                    amount=self._maintenance_fee,
                    reason=(
                        f"Insufficient balance to collect maintenance fee.  "
                        f"Balance: {self._balance} {self._currency}, "
                        f"Fee: {self._maintenance_fee} {self._currency}."
                    ),
                )
            self._commit(
                amount=self._maintenance_fee,
                new_balance=self._balance - self._maintenance_fee,
                transaction_type=TransactionType.FEE_DEDUCTION,
                description="Monthly maintenance fee.",
            )
            return FeeCollectionResult(
                success=True,
                amount=self._maintenance_fee,
                reason="Monthly maintenance fee collected.",
            )

    # ── Override withdrawal check ─────────────────────────────────────────────

    def _check_withdrawal(self, amount: Decimal) -> None:
        """Allow withdrawal up to ``balance + overdraft_limit``."""
        available = self._balance + self._overdraft_limit
        if amount > available:
            raise OverdraftLimitExceededError(
                f"Withdrawal exceeds available balance including overdraft.  "
                f"Balance: {self._balance} {self._currency}, "
                f"Overdraft limit: {self._overdraft_limit} {self._currency}, "
                f"Available: {available} {self._currency}, "
                f"Requested: {amount} {self._currency}."
            )


# ── HighYieldAccount ──────────────────────────────────────────────────────────


class HighYieldAccount(Account):
    """High-yield account with a minimum-balance requirement for interest eligibility.

    Interest policy
    ---------------
    Simple interest at a configurable high rate, credited per period **only
    when** the current balance is ≥ ``minimum_balance``.  If the balance
    falls below the minimum, no interest is credited for that period.

    Fee policy
    ----------
    A ``below_minimum_fee`` is charged when the balance is below
    ``minimum_balance``.  If the balance is also insufficient to pay the fee,
    the fee is **skipped** (balance unchanged, no ledger entry).

    Withdrawal policy
    -----------------
    Standard: no overdraft.  Withdrawals that would reduce the balance below
    zero are rejected.

    Parameters
    ----------
    holder_name:
        Non-empty account holder name.
    currency:
        ISO 4217 currency code.
    initial_balance:
        Non-negative opening balance (default ``Decimal("0")``).
    interest_rate:
        Non-negative annual interest rate (default 7 %).
    minimum_balance:
        Non-negative minimum balance for interest eligibility
        (default ``Decimal("1000.00")``).
    below_minimum_fee:
        Non-negative fee charged when balance < minimum_balance
        (default ``Decimal("25.00")``).
    ledger:
        Optional shared ledger instance.

    Notes
    -----
    Default values are demonstration values only.
    """

    DEFAULT_INTEREST_RATE: Decimal = Decimal("0.07")
    DEFAULT_MINIMUM_BALANCE: Decimal = Decimal("1000.00")
    DEFAULT_BELOW_MINIMUM_FEE: Decimal = Decimal("25.00")

    def __init__(
        self,
        holder_name: str,
        currency: str,
        initial_balance: Decimal = Decimal("0"),
        interest_rate: Decimal = DEFAULT_INTEREST_RATE,
        minimum_balance: Decimal = DEFAULT_MINIMUM_BALANCE,
        below_minimum_fee: Decimal = DEFAULT_BELOW_MINIMUM_FEE,
        ledger: Optional[Ledger] = None,
    ) -> None:
        for name, val in [
            ("interest_rate", interest_rate),
            ("minimum_balance", minimum_balance),
            ("below_minimum_fee", below_minimum_fee),
        ]:
            if not isinstance(val, Decimal):
                raise AccountConfigurationError(
                    f"{name} must be Decimal, got {type(val).__name__}."
                )
            if not val.is_finite() or val < Decimal("0"):
                raise AccountConfigurationError(
                    f"{name} must be a non-negative finite Decimal, got {val!s}."
                )

        super().__init__(holder_name, currency, initial_balance, ledger)
        self._interest_rate: Decimal = interest_rate
        self._minimum_balance: Decimal = minimum_balance
        self._below_minimum_fee: Decimal = below_minimum_fee

    @property
    def interest_rate(self) -> Decimal:
        """Annual interest rate as a proportion (read-only)."""
        return self._interest_rate

    @property
    def minimum_balance(self) -> Decimal:
        """Minimum balance required for interest eligibility (read-only)."""
        return self._minimum_balance

    @property
    def below_minimum_fee(self) -> Decimal:
        """Fee applied when balance is below ``minimum_balance`` (read-only)."""
        return self._below_minimum_fee

    @property
    def is_eligible_for_interest(self) -> bool:
        """``True`` if the current balance meets the minimum balance requirement."""
        with self._lock:
            return self._balance >= self._minimum_balance

    # ── Abstract implementations ──────────────────────────────────────────────

    def accrue_interest(self) -> Optional[LedgerEntry]:
        """Credit high-yield interest, subject to minimum balance eligibility.

        Returns ``None`` if the balance is below ``minimum_balance`` or if
        the computed interest rounds to zero.
        """
        with self._lock:
            if self._balance < self._minimum_balance:
                return None  # Eligibility not met — no interest this period.
            interest = round_for_currency(
                self._balance * self._interest_rate, self._currency
            )
            if interest <= Decimal("0"):
                return None
            return self._commit(
                amount=interest,
                new_balance=self._balance + interest,
                transaction_type=TransactionType.INTEREST_CREDIT,
                description=(
                    f"High-yield interest at "
                    f"{self._interest_rate * 100:.4f}% per period."
                ),
            )

    def deduct_fees(self) -> FeeCollectionResult:
        """Deduct the below-minimum-balance fee when applicable.

        If the balance meets ``minimum_balance``, no fee is charged.
        If the balance is below ``minimum_balance`` but also below
        ``below_minimum_fee``, the fee is **skipped** (balance unchanged,
        no ledger entry).

        Returns
        -------
        FeeCollectionResult
            Outcome of the fee collection attempt.
        """
        with self._lock:
            if self._balance >= self._minimum_balance:
                return FeeCollectionResult(
                    success=True,
                    amount=Decimal("0"),
                    reason="Balance meets minimum; no fee applicable.",
                )
            if self._below_minimum_fee <= Decimal("0"):
                return FeeCollectionResult(
                    success=True,
                    amount=Decimal("0"),
                    reason="No below-minimum fee configured.",
                )
            if self._balance < self._below_minimum_fee:
                return FeeCollectionResult(
                    success=False,
                    amount=self._below_minimum_fee,
                    reason=(
                        f"Insufficient balance to collect below-minimum fee.  "
                        f"Balance: {self._balance} {self._currency}, "
                        f"Fee: {self._below_minimum_fee} {self._currency}."
                    ),
                )
            self._commit(
                amount=self._below_minimum_fee,
                new_balance=self._balance - self._below_minimum_fee,
                transaction_type=TransactionType.FEE_DEDUCTION,
                description="Below-minimum balance fee.",
            )
            return FeeCollectionResult(
                success=True,
                amount=self._below_minimum_fee,
                reason="Below-minimum balance fee collected.",
            )

    # ── Override withdrawal check ─────────────────────────────────────────────

    def _check_withdrawal(self, amount: Decimal) -> None:
        """Reject withdrawals that would overdraft the account."""
        if amount > self._balance:
            raise InsufficientFundsError(
                f"HighYieldAccount does not permit overdraft.  "
                f"Balance: {self._balance} {self._currency}, "
                f"Requested: {amount} {self._currency}."
            )
