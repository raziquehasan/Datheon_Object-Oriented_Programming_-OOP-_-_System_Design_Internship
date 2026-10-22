"""
Tests for currency validation, Decimal precision, and exchange-rate service.

Covers requirements:
15. Currency separation (accounts in different currencies are independent)
19. Correct rounding of monetary amounts (currency-specific precision)
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from banking import (
    ExchangeRateService,
    SavingsAccount,
    SUPPORTED_CURRENCIES,
    validate_currency,
    validate_amount,
    round_for_currency,
)
from banking.exceptions import (
    CurrencyMismatchError,
    InvalidAmountError,
    UnsupportedCurrencyError,
)


# ── Currency validation ────────────────────────────────────────────────────────


def test_all_supported_currencies_validate():
    for code in ["INR", "USD", "EUR", "GBP"]:
        cfg = validate_currency(code)
        assert cfg.code == code


def test_unsupported_currency_raises():
    with pytest.raises(UnsupportedCurrencyError):
        validate_currency("XYZ")


def test_lowercase_currency_rejected():
    with pytest.raises(UnsupportedCurrencyError):
        validate_currency("usd")


def test_empty_currency_rejected():
    with pytest.raises(UnsupportedCurrencyError):
        validate_currency("")


# ── Amount validation ─────────────────────────────────────────────────────────


def test_valid_amount_passes():
    result = validate_amount(Decimal("100.50"), "USD")
    assert result == Decimal("100.50")


def test_zero_amount_rejected():
    with pytest.raises(InvalidAmountError):
        validate_amount(Decimal("0"), "USD")


def test_negative_amount_rejected():
    with pytest.raises(InvalidAmountError):
        validate_amount(Decimal("-1.00"), "USD")


def test_nan_amount_rejected():
    with pytest.raises(InvalidAmountError):
        validate_amount(Decimal("NaN"), "USD")


def test_infinity_amount_rejected():
    with pytest.raises(InvalidAmountError):
        validate_amount(Decimal("Infinity"), "USD")


def test_float_amount_rejected():
    with pytest.raises(InvalidAmountError):
        validate_amount(100.0, "USD")  # type: ignore[arg-type]


# ── Currency rounding ─────────────────────────────────────────────────────────


def test_usd_rounds_to_2_decimal_places():
    result = round_for_currency(Decimal("1.005"), "USD")
    assert result == Decimal("1.01")  # ROUND_HALF_UP


def test_inr_rounds_to_2_decimal_places():
    result = round_for_currency(Decimal("99.999"), "INR")
    assert result == Decimal("100.00")


def test_eur_rounds_to_2_decimal_places():
    result = round_for_currency(Decimal("0.001"), "EUR")
    assert result == Decimal("0.00")


def test_gbp_rounds_to_2_decimal_places():
    result = round_for_currency(Decimal("0.995"), "GBP")
    assert result == Decimal("1.00")


# ── 15. Currency separation ────────────────────────────────────────────────────


def test_accounts_in_different_currencies_are_independent():
    inr_acc = SavingsAccount("Alice", "INR", Decimal("10000.00"))
    usd_acc = SavingsAccount("Bob", "USD", Decimal("100.00"))

    inr_acc.deposit(Decimal("5000.00"))
    usd_acc.deposit(Decimal("50.00"))

    assert inr_acc.balance == Decimal("15000.00")
    assert usd_acc.balance == Decimal("150.00")
    assert inr_acc.currency == "INR"
    assert usd_acc.currency == "USD"


def test_account_currency_stored_correctly():
    for code in ["INR", "USD", "EUR", "GBP"]:
        acc = SavingsAccount("Test", code, Decimal("0"))
        assert acc.currency == code


# ── ExchangeRateService ────────────────────────────────────────────────────────


def test_register_and_convert():
    svc = ExchangeRateService()
    svc.register_rate("USD", "INR", Decimal("83.50"))
    result = svc.convert(Decimal("1.00"), "USD", "INR")
    assert result == Decimal("83.50")


def test_inverse_rate_registered_automatically():
    svc = ExchangeRateService()
    svc.register_rate("USD", "INR", Decimal("83.50"))
    # Inverse: INR → USD
    assert svc.has_rate("INR", "USD")
    result = svc.convert(Decimal("83.50"), "INR", "USD")
    assert result == Decimal("1.00")


def test_convert_same_currency():
    svc = ExchangeRateService()
    result = svc.convert(Decimal("100.00"), "USD", "USD")
    assert result == Decimal("100.00")


def test_convert_without_registered_rate_raises():
    svc = ExchangeRateService()
    with pytest.raises(CurrencyMismatchError):
        svc.convert(Decimal("100.00"), "USD", "EUR")


def test_register_unsupported_currency_raises():
    svc = ExchangeRateService()
    with pytest.raises(UnsupportedCurrencyError):
        svc.register_rate("USD", "XYZ", Decimal("1.5"))


def test_register_negative_rate_raises():
    svc = ExchangeRateService()
    with pytest.raises(ValueError):
        svc.register_rate("USD", "EUR", Decimal("-1.0"))


def test_register_zero_rate_raises():
    svc = ExchangeRateService()
    with pytest.raises(ValueError):
        svc.register_rate("USD", "EUR", Decimal("0"))


def test_register_nan_rate_raises():
    svc = ExchangeRateService()
    with pytest.raises(ValueError):
        svc.register_rate("USD", "EUR", Decimal("NaN"))


def test_register_float_rate_raises():
    svc = ExchangeRateService()
    with pytest.raises(ValueError):
        svc.register_rate("USD", "EUR", 1.1)  # type: ignore[arg-type]


def test_conversion_result_rounded_to_target_currency_precision():
    svc = ExchangeRateService()
    svc.register_rate("USD", "INR", Decimal("83.33"))
    # 1.00 * 83.33 = 83.33 → rounded to 2 dp → 83.33
    result = svc.convert(Decimal("1.00"), "USD", "INR")
    assert result == Decimal("83.33")
    # 0.01 * 83.33 = 0.8333 → ROUND_HALF_UP → 0.83
    result2 = svc.convert(Decimal("0.01"), "USD", "INR")
    assert result2 == Decimal("0.83")


def test_has_rate_false_without_registration():
    svc = ExchangeRateService()
    assert svc.has_rate("USD", "EUR") is False


def test_has_rate_true_after_registration():
    svc = ExchangeRateService()
    svc.register_rate("USD", "EUR", Decimal("0.92"))
    assert svc.has_rate("USD", "EUR") is True
    assert svc.has_rate("EUR", "USD") is True  # inverse also registered
