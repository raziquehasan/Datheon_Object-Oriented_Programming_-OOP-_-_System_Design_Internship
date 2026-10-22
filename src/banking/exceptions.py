"""
Custom exception hierarchy for the banking ledger engine.

All exceptions inherit from BankingError so callers can catch the entire
family with a single except clause or target specific subtypes.
"""


class BankingError(Exception):
    """Base exception for all banking-engine errors."""


# ── Account configuration ────────────────────────────────────────────────────


class InvalidAccountError(BankingError):
    """Raised when account creation parameters are invalid (empty name, etc.)."""


class AccountConfigurationError(BankingError):
    """Raised when account-level configuration values are invalid (negative
    interest rates, fees, overdraft limits, minimum balances, etc.)."""


# ── Currency ──────────────────────────────────────────────────────────────────


class UnsupportedCurrencyError(BankingError):
    """Raised when a currency code is not in the supported set."""


class CurrencyMismatchError(BankingError):
    """Raised when an operation attempts cross-currency arithmetic without an
    explicitly registered exchange rate."""


# ── Amounts ───────────────────────────────────────────────────────────────────


class InvalidAmountError(BankingError):
    """Raised when a monetary amount is non-positive, non-finite (NaN /
    infinity), or has the wrong type."""


# ── Funds / balance ───────────────────────────────────────────────────────────


class InsufficientFundsError(BankingError):
    """Raised when a withdrawal would exceed the account's permitted balance."""


class OverdraftLimitExceededError(InsufficientFundsError):
    """Raised when a withdrawal would exceed the configured overdraft limit on
    a CheckingAccount."""


class MinimumBalanceViolationError(BankingError):
    """Raised when an operation would violate a HighYieldAccount's minimum
    balance constraint (reserved for future hard-reject policy)."""


# ── Transactions ──────────────────────────────────────────────────────────────


class InvalidTransactionTypeError(BankingError):
    """Raised when an unrecognised TransactionType is supplied."""


# ── Atomicity ─────────────────────────────────────────────────────────────────


class AtomicOperationError(BankingError):
    """Raised when the atomic commit of a balance update + ledger entry fails.
    The balance is always rolled back to its pre-operation value before this
    exception propagates."""
