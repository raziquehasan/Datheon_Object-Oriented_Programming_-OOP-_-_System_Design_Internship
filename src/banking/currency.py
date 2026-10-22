"""
Currency configuration, validation, and exchange-rate service.

Design notes
------------
* Only currencies listed in ``SUPPORTED_CURRENCIES`` are accepted anywhere in
  the engine.  Passing an unrecognised code raises
  :class:`~banking.exceptions.UnsupportedCurrencyError`.
* All monetary amounts are represented as ``decimal.Decimal`` and rounded to
  the correct number of decimal places for the target currency using
  ``ROUND_HALF_UP``.
* Cross-currency arithmetic is **never** performed implicitly.  The
  :class:`ExchangeRateService` requires rates to be registered explicitly
  before ``convert()`` is called; it raises
  :class:`~banking.exceptions.CurrencyMismatchError` if no rate is registered.
* Exchange rates are stored as ``Decimal`` values and validated to be positive
  and finite on registration.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Dict, Tuple

from .exceptions import (
    CurrencyMismatchError,
    InvalidAmountError,
    UnsupportedCurrencyError,
)


# ── Currency configuration ────────────────────────────────────────────────────


@dataclass(frozen=True)
class CurrencyConfig:
    """Static configuration for a single currency.

    Attributes
    ----------
    code:
        ISO 4217 currency code (e.g. ``"USD"``).
    name:
        Full currency name.
    symbol:
        Display symbol (e.g. ``"$"``).
    decimal_places:
        Number of fractional digits used for rounding (e.g. ``2`` for cents).
    """

    code: str
    name: str
    symbol: str
    decimal_places: int


#: Registry of supported currencies.  Add entries here to extend support.
SUPPORTED_CURRENCIES: Dict[str, CurrencyConfig] = {
    "INR": CurrencyConfig("INR", "Indian Rupee", "₹", 2),
    "USD": CurrencyConfig("USD", "US Dollar", "$", 2),
    "EUR": CurrencyConfig("EUR", "Euro", "€", 2),
    "GBP": CurrencyConfig("GBP", "British Pound Sterling", "£", 2),
}

# Pre-computed quantize targets (e.g. Decimal("0.01") for 2 decimal places).
_QUANTIZE: Dict[str, Decimal] = {
    code: Decimal(10) ** -cfg.decimal_places
    for code, cfg in SUPPORTED_CURRENCIES.items()
}


# ── Validation helpers ────────────────────────────────────────────────────────


def validate_currency(code: str) -> CurrencyConfig:
    """Return the :class:`CurrencyConfig` for *code*, or raise.

    Parameters
    ----------
    code:
        ISO 4217 currency code string.

    Raises
    ------
    UnsupportedCurrencyError
        If *code* is not in :data:`SUPPORTED_CURRENCIES`.
    """
    if code not in SUPPORTED_CURRENCIES:
        supported = ", ".join(sorted(SUPPORTED_CURRENCIES))
        raise UnsupportedCurrencyError(
            f"Unsupported currency code {code!r}.  "
            f"Supported currencies: {supported}."
        )
    return SUPPORTED_CURRENCIES[code]


def round_for_currency(amount: Decimal, currency_code: str) -> Decimal:
    """Round *amount* to the correct number of decimal places for *currency_code*.

    Uses ``ROUND_HALF_UP`` (the conventional banking rounding mode).

    Parameters
    ----------
    amount:
        A finite ``Decimal`` value.
    currency_code:
        Validated ISO 4217 code (validated by :func:`validate_currency`).

    Returns
    -------
    Decimal
        Rounded amount.
    """
    validate_currency(currency_code)
    return amount.quantize(_QUANTIZE[currency_code], rounding=ROUND_HALF_UP)


def validate_amount(amount: Decimal, currency_code: str) -> Decimal:
    """Validate and normalise a monetary amount for *currency_code*.

    Parameters
    ----------
    amount:
        The amount to validate.  Must be a positive, finite ``Decimal``.
    currency_code:
        ISO 4217 code; validated implicitly.

    Returns
    -------
    Decimal
        The rounded, validated amount.

    Raises
    ------
    InvalidAmountError
        If *amount* is not a ``Decimal``, is non-finite, or is ≤ 0.
    UnsupportedCurrencyError
        If *currency_code* is unrecognised.
    """
    if not isinstance(amount, Decimal):
        raise InvalidAmountError(
            f"Amount must be decimal.Decimal, got {type(amount).__name__}."
        )
    if not amount.is_finite():
        raise InvalidAmountError(
            f"Amount must be a finite number (no NaN or Infinity), got {amount!s}."
        )
    if amount <= Decimal("0"):
        raise InvalidAmountError(
            f"Amount must be positive (> 0), got {amount!s}."
        )
    return round_for_currency(amount, currency_code)


# ── Exchange-rate service ─────────────────────────────────────────────────────


class ExchangeRateService:
    """Explicit exchange-rate registry for currency conversion.

    Rates must be registered with :meth:`register_rate` before
    :meth:`convert` can be called.  The service *never* invents rates or
    falls back to hard-coded values.

    Registering a rate ``from_currency → to_currency`` automatically stores
    the inverse rate ``to_currency → from_currency`` computed from the
    supplied value.

    All rates are stored as ``Decimal`` and validated to be positive and
    finite.

    Example
    -------
    ::

        svc = ExchangeRateService()
        svc.register_rate("USD", "INR", Decimal("83.50"))
        inr = svc.convert(Decimal("100"), "USD", "INR")  # → Decimal("8350.00")
    """

    def __init__(self) -> None:
        self._rates: Dict[Tuple[str, str], Decimal] = {}

    def register_rate(
        self,
        from_currency: str,
        to_currency: str,
        rate: Decimal,
    ) -> None:
        """Register an explicit exchange rate and its inverse.

        Parameters
        ----------
        from_currency:
            Source ISO 4217 code.
        to_currency:
            Target ISO 4217 code.
        rate:
            Positive, finite ``Decimal`` exchange rate
            (units of *to_currency* per one unit of *from_currency*).

        Raises
        ------
        UnsupportedCurrencyError
            If either currency code is unrecognised.
        ValueError
            If *rate* is not a positive finite ``Decimal``.
        """
        validate_currency(from_currency)
        validate_currency(to_currency)
        if not isinstance(rate, Decimal):
            raise ValueError(
                f"Exchange rate must be decimal.Decimal, got {type(rate).__name__}."
            )
        if not rate.is_finite() or rate <= Decimal("0"):
            raise ValueError(
                f"Exchange rate must be positive and finite, got {rate!s}."
            )

        self._rates[(from_currency, to_currency)] = rate
        # Compute and store the inverse with 6 decimal places of precision.
        inverse = (Decimal("1") / rate).quantize(
            Decimal("0.000001"), rounding=ROUND_HALF_UP
        )
        self._rates[(to_currency, from_currency)] = inverse

    def has_rate(self, from_currency: str, to_currency: str) -> bool:
        """Return ``True`` if a rate is registered for this pair."""
        if from_currency == to_currency:
            return True
        return (from_currency, to_currency) in self._rates

    def convert(
        self,
        amount: Decimal,
        from_currency: str,
        to_currency: str,
    ) -> Decimal:
        """Convert *amount* from *from_currency* to *to_currency*.

        Parameters
        ----------
        amount:
            Positive, finite ``Decimal`` amount in *from_currency*.
        from_currency:
            Source ISO 4217 code.
        to_currency:
            Target ISO 4217 code.

        Returns
        -------
        Decimal
            Converted amount, rounded to the precision of *to_currency*.

        Raises
        ------
        CurrencyMismatchError
            If no rate has been registered for this currency pair.
        InvalidAmountError
            If *amount* is invalid.
        """
        validate_amount(amount, from_currency)

        if from_currency == to_currency:
            return round_for_currency(amount, to_currency)

        key = (from_currency, to_currency)
        if key not in self._rates:
            raise CurrencyMismatchError(
                f"No exchange rate registered for {from_currency} → {to_currency}.  "
                f"Call register_rate() before converting."
            )

        converted = amount * self._rates[key]
        return round_for_currency(converted, to_currency)
