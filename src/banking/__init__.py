"""
banking — Multi-Currency Banking & Ledger Engine.

Public API surface:
"""

from .accounts import Account, CheckingAccount, HighYieldAccount, SavingsAccount
from .currency import (
    SUPPORTED_CURRENCIES,
    CurrencyConfig,
    ExchangeRateService,
    round_for_currency,
    validate_amount,
    validate_currency,
)
from .exceptions import (
    AccountConfigurationError,
    AtomicOperationError,
    BankingError,
    CurrencyMismatchError,
    InsufficientFundsError,
    InvalidAccountError,
    InvalidAmountError,
    InvalidTransactionTypeError,
    MinimumBalanceViolationError,
    OverdraftLimitExceededError,
    UnsupportedCurrencyError,
)
from .ledger import Ledger
from .models import AccountSummary, FeeCollectionResult, LedgerEntry, TransactionType
from .reporting import StatementExporter, SummaryCalculator, TransactionFilter
from .services import AccountRegistry, BankService

__all__ = [
    # Accounts
    "Account",
    "SavingsAccount",
    "CheckingAccount",
    "HighYieldAccount",
    # Currency
    "SUPPORTED_CURRENCIES",
    "CurrencyConfig",
    "ExchangeRateService",
    "validate_currency",
    "validate_amount",
    "round_for_currency",
    # Exceptions
    "BankingError",
    "InvalidAccountError",
    "AccountConfigurationError",
    "UnsupportedCurrencyError",
    "CurrencyMismatchError",
    "InvalidAmountError",
    "InsufficientFundsError",
    "OverdraftLimitExceededError",
    "MinimumBalanceViolationError",
    "InvalidTransactionTypeError",
    "AtomicOperationError",
    # Ledger
    "Ledger",
    # Models
    "TransactionType",
    "LedgerEntry",
    "FeeCollectionResult",
    "AccountSummary",
    # Reporting
    "TransactionFilter",
    "SummaryCalculator",
    "StatementExporter",
    # Services
    "AccountRegistry",
    "BankService",
]

__version__ = "1.0.0"
