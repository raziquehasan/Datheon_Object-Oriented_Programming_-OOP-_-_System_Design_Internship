"""
High-level banking service and account registry.

``BankService`` is the primary entry point for application code.  It acts as:

* **Factory**: creates and registers account instances with validated
  configuration.  An account that fails construction is *never* registered.
* **Polymorphic processor**: ``process_interest_and_fees()`` calls each
  account's ``accrue_interest()`` and ``deduct_fees()`` through the common
  :class:`~banking.accounts.Account` interface, with no conditional type
  inspection.
* **Registry wrapper**: provides ``get_account()`` for lookup by account ID.

The :class:`AccountRegistry` is thread-safe and the ``BankService`` methods
are safe to call from multiple threads simultaneously.
"""

from __future__ import annotations

import threading
from decimal import Decimal
from typing import Dict, List, Optional

from .accounts import Account, CheckingAccount, HighYieldAccount, SavingsAccount
from .currency import ExchangeRateService
from .exceptions import InvalidAccountError
from .models import FeeCollectionResult, LedgerEntry


# ── Account registry ──────────────────────────────────────────────────────────


class AccountRegistry:
    """Thread-safe mapping from account ID to :class:`~banking.accounts.Account`.

    Accounts are registered once at creation time and never removed (in this
    in-memory implementation).
    """

    def __init__(self) -> None:
        self._accounts: Dict[str, Account] = {}
        self._lock: threading.RLock = threading.RLock()

    def register(self, account: Account) -> None:
        """Add *account* to the registry.

        Parameters
        ----------
        account:
            A fully constructed :class:`~banking.accounts.Account` instance.
        """
        with self._lock:
            self._accounts[account.account_id] = account

    def get(self, account_id: str) -> Account:
        """Return the account with *account_id*, or raise.

        Raises
        ------
        InvalidAccountError
            If no account with *account_id* is registered.
        """
        with self._lock:
            if account_id not in self._accounts:
                raise InvalidAccountError(
                    f"Account not found: {account_id!r}."
                )
            return self._accounts[account_id]

    def all_accounts(self) -> List[Account]:
        """Return a snapshot list of all registered accounts."""
        with self._lock:
            return list(self._accounts.values())

    def __len__(self) -> int:
        with self._lock:
            return len(self._accounts)


# ── Bank service ──────────────────────────────────────────────────────────────


class BankService:
    """Factory, registry wrapper, and polymorphic transaction processor.

    Parameters
    ----------
    exchange_rate_service:
        Optional :class:`~banking.currency.ExchangeRateService` instance for
        currency conversion.  If ``None``, a new empty service is created.

    Example
    -------
    ::

        from decimal import Decimal
        from banking import BankService

        bank = BankService()
        savings = bank.create_savings_account("Alice", "INR", Decimal("5000"))
        savings.deposit(Decimal("1000"))
        results = bank.process_interest_and_fees()
    """

    def __init__(
        self,
        exchange_rate_service: Optional[ExchangeRateService] = None,
    ) -> None:
        self._registry = AccountRegistry()
        self._exchange_rate_service: ExchangeRateService = (
            exchange_rate_service
            if exchange_rate_service is not None
            else ExchangeRateService()
        )

    # ── Account factories ─────────────────────────────────────────────────────

    def create_savings_account(
        self,
        holder_name: str,
        currency: str,
        initial_balance: Decimal = Decimal("0"),
        interest_rate: Decimal = SavingsAccount.DEFAULT_INTEREST_RATE,
    ) -> SavingsAccount:
        """Create, register, and return a :class:`~banking.accounts.SavingsAccount`.

        Raises any configuration or validation exception *before* the account
        is registered; a failed creation leaves the registry unchanged.
        """
        account = SavingsAccount(
            holder_name=holder_name,
            currency=currency,
            initial_balance=initial_balance,
            interest_rate=interest_rate,
        )
        self._registry.register(account)
        return account

    def create_checking_account(
        self,
        holder_name: str,
        currency: str,
        initial_balance: Decimal = Decimal("0"),
        maintenance_fee: Decimal = CheckingAccount.DEFAULT_MAINTENANCE_FEE,
        overdraft_limit: Decimal = Decimal("0"),
        interest_rate: Decimal = CheckingAccount.DEFAULT_INTEREST_RATE,
    ) -> CheckingAccount:
        """Create, register, and return a :class:`~banking.accounts.CheckingAccount`."""
        account = CheckingAccount(
            holder_name=holder_name,
            currency=currency,
            initial_balance=initial_balance,
            maintenance_fee=maintenance_fee,
            overdraft_limit=overdraft_limit,
            interest_rate=interest_rate,
        )
        self._registry.register(account)
        return account

    def create_high_yield_account(
        self,
        holder_name: str,
        currency: str,
        initial_balance: Decimal = Decimal("0"),
        interest_rate: Decimal = HighYieldAccount.DEFAULT_INTEREST_RATE,
        minimum_balance: Decimal = HighYieldAccount.DEFAULT_MINIMUM_BALANCE,
        below_minimum_fee: Decimal = HighYieldAccount.DEFAULT_BELOW_MINIMUM_FEE,
    ) -> HighYieldAccount:
        """Create, register, and return a :class:`~banking.accounts.HighYieldAccount`."""
        account = HighYieldAccount(
            holder_name=holder_name,
            currency=currency,
            initial_balance=initial_balance,
            interest_rate=interest_rate,
            minimum_balance=minimum_balance,
            below_minimum_fee=below_minimum_fee,
        )
        self._registry.register(account)
        return account

    # ── Polymorphic processor ─────────────────────────────────────────────────

    def process_interest_and_fees(self) -> Dict[str, dict]:
        """Apply interest and fees to every registered account polymorphically.

        Calls ``account.accrue_interest()`` and ``account.deduct_fees()``
        through the :class:`~banking.accounts.Account` interface without
        inspecting the concrete type.

        Returns
        -------
        dict[str, dict]
            Mapping of account ID → processing summary with keys:

            * ``holder`` — account holder name.
            * ``account_type`` — concrete class name.
            * ``currency`` — account currency.
            * ``balance_after`` — balance after processing (string).
            * ``interest_entry`` — serialised ledger entry dict or ``None``.
            * ``fee_result`` — :class:`~banking.models.FeeCollectionResult`
              dict with ``success``, ``amount``, ``reason`` keys.
        """
        results: Dict[str, dict] = {}
        for account in self._registry.all_accounts():
            interest_entry: Optional[LedgerEntry] = account.accrue_interest()
            fee_result: FeeCollectionResult = account.deduct_fees()

            results[account.account_id] = {
                "holder": account.holder_name,
                "account_type": type(account).__name__,
                "currency": account.currency,
                "balance_after": str(account.balance),
                "interest_entry": (
                    {
                        "transaction_id": interest_entry.transaction_id,
                        "amount": str(interest_entry.amount),
                        "balance_after": str(interest_entry.balance_after),
                        "description": interest_entry.description,
                    }
                    if interest_entry is not None
                    else None
                ),
                "fee_result": {
                    "success": fee_result.success,
                    "amount": str(fee_result.amount),
                    "reason": fee_result.reason,
                },
            }

        return results

    # ── Lookup ────────────────────────────────────────────────────────────────

    def get_account(self, account_id: str) -> Account:
        """Return the account with *account_id*.

        Raises
        ------
        InvalidAccountError
            If no such account is registered.
        """
        return self._registry.get(account_id)

    @property
    def exchange_rate_service(self) -> ExchangeRateService:
        """The :class:`~banking.currency.ExchangeRateService` used by this bank."""
        return self._exchange_rate_service

    @property
    def account_count(self) -> int:
        """Number of accounts currently registered."""
        return len(self._registry)
