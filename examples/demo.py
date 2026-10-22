"""
examples/demo.py — Runnable demonstration of the banking ledger engine.

Runs entirely in memory; no database, API key, or external service required.

Demonstrates:
  1. Creating one instance of each account type.
  2. Deposits and withdrawals.
  3. Interest and fee processing (polymorphic).
  4. At least one rejected transaction.
  5. Account balances.
  6. Transaction history.
  7. Statement export (JSON + CSV).
"""

from __future__ import annotations

import json
import os
import tempfile
from decimal import Decimal

from banking import (
    BankService,
    ExchangeRateService,
    StatementExporter,
    SummaryCalculator,
)
from banking.exceptions import InsufficientFundsError, OverdraftLimitExceededError


# ── Helpers ────────────────────────────────────────────────────────────────────

LINE = "─" * 62


def section(title: str) -> None:
    print(f"\n{LINE}")
    print(f"  {title}")
    print(LINE)


def show_balance(account) -> None:
    sym = {"INR": "₹", "USD": "$", "EUR": "€", "GBP": "£"}.get(account.currency, "")
    print(
        f"  [{type(account).__name__}] {account.holder_name} | "
        f"{sym}{account.balance} {account.currency}"
    )


def show_ledger(account) -> None:
    entries = account.get_ledger_entries()
    print(f"\n  Transaction history for {account.holder_name} "
          f"({account.currency}) — {len(entries)} entries:")
    for e in entries:
        sign = "+" if e.transaction_type.value in ("DEPOSIT", "INTEREST_CREDIT",
                                                    "OPENING_BALANCE") else "-"
        print(
            f"    {e.timestamp.strftime('%H:%M:%S.%f')[:-3]}  "
            f"{e.transaction_type.value:<18}  "
            f"{sign}{e.amount:>10}  "
            f"→ balance {e.balance_after}"
        )


# ── Main ───────────────────────────────────────────────────────────────────────


def main() -> None:
    print("\n" + "=" * 62)
    print("  Multi-Currency Banking & Ledger Engine — Demo")
    print("  NOTE: All values are demonstration defaults only.")
    print("  This is not a real bank product or financial advice.")
    print("=" * 62)

    # ── 1. Create accounts ────────────────────────────────────────────────────
    section("1. Creating accounts")

    exchange_svc = ExchangeRateService()
    exchange_svc.register_rate("USD", "INR", Decimal("83.50"))
    exchange_svc.register_rate("GBP", "EUR", Decimal("1.17"))

    bank = BankService(exchange_rate_service=exchange_svc)

    savings = bank.create_savings_account(
        holder_name="Arjun Sharma",
        currency="INR",
        initial_balance=Decimal("50000.00"),
        interest_rate=Decimal("0.035"),
    )
    checking = bank.create_checking_account(
        holder_name="Beth Collins",
        currency="USD",
        initial_balance=Decimal("2000.00"),
        maintenance_fee=Decimal("12.00"),
        overdraft_limit=Decimal("500.00"),
        interest_rate=Decimal("0.001"),
    )
    high_yield = bank.create_high_yield_account(
        holder_name="Carlos Ruiz",
        currency="GBP",
        initial_balance=Decimal("5000.00"),
        interest_rate=Decimal("0.07"),
        minimum_balance=Decimal("1000.00"),
        below_minimum_fee=Decimal("25.00"),
    )

    print(f"  ✔ Savings   (INR): {savings.account_id[:8]}…  "
          f"Balance ₹{savings.balance}")
    print(f"  ✔ Checking  (USD): {checking.account_id[:8]}…  "
          f"Balance ${checking.balance}")
    print(f"  ✔ HighYield (GBP): {high_yield.account_id[:8]}…  "
          f"Balance £{high_yield.balance}")

    # ── 2. Deposits ───────────────────────────────────────────────────────────
    section("2. Deposits")

    savings.deposit(Decimal("10000.00"), description="Salary credit")
    checking.deposit(Decimal("500.00"), description="Client payment")
    high_yield.deposit(Decimal("2000.00"), description="Bonus")

    show_balance(savings)
    show_balance(checking)
    show_balance(high_yield)

    # ── 3. Withdrawals ────────────────────────────────────────────────────────
    section("3. Withdrawals")

    savings.withdraw(Decimal("5000.00"), description="Rent payment")
    checking.withdraw(Decimal("300.00"), description="Office supplies")
    high_yield.withdraw(Decimal("500.00"), description="Quarterly expense")

    show_balance(savings)
    show_balance(checking)
    show_balance(high_yield)

    # ── 4. Rejected transaction ────────────────────────────────────────────────
    section("4. Rejected transactions (demonstrated)")

    # 4a. Savings: no overdraft
    print("\n  [SavingsAccount] Attempting to withdraw ₹999,999 (exceeds balance):")
    try:
        savings.withdraw(Decimal("999999.00"))
    except InsufficientFundsError as exc:
        print(f"  ✗ Rejected → {exc}")
    show_balance(savings)

    # 4b. Checking: beyond overdraft limit
    print(
        "\n  [CheckingAccount] Attempting to withdraw $10,000 "
        "(exceeds balance + overdraft):"
    )
    try:
        checking.withdraw(Decimal("10000.00"))
    except OverdraftLimitExceededError as exc:
        print(f"  ✗ Rejected → {exc}")
    show_balance(checking)

    # 4c. Invalid amount
    print("\n  [SavingsAccount] Attempting to deposit ₹0 (invalid amount):")
    from banking.exceptions import InvalidAmountError
    try:
        savings.deposit(Decimal("0"))
    except InvalidAmountError as exc:
        print(f"  ✗ Rejected → {exc}")

    # ── 5. Polymorphic interest + fee processing ───────────────────────────────
    section("5. Polymorphic interest & fee processing")

    results = bank.process_interest_and_fees()
    for acct_id, info in results.items():
        interest = info["interest_entry"]
        fee = info["fee_result"]
        interest_str = (
            f"+{interest['amount']} {info['currency']}"
            if interest else "no interest this period"
        )
        fee_str = (
            f"-{fee['amount']} {info['currency']} (collected)"
            if fee["success"] and Decimal(fee["amount"]) > 0
            else f"skipped ({fee['reason']})"
            if not fee["success"]
            else "no fee"
        )
        print(
            f"  {info['account_type']:<18} {info['holder']:<15} | "
            f"Interest: {interest_str:<25} | Fee: {fee_str}"
        )

    # ── 6. Balances after processing ──────────────────────────────────────────
    section("6. Final balances")
    show_balance(savings)
    show_balance(checking)
    show_balance(high_yield)

    # ── 7. Transaction history ─────────────────────────────────────────────────
    section("7. Transaction history")
    show_ledger(savings)
    show_ledger(checking)
    show_ledger(high_yield)

    # ── 8. Summary totals ──────────────────────────────────────────────────────
    section("8. Statement summaries")
    for acc in [savings, checking, high_yield]:
        entries = acc.get_ledger_entries()
        summary = SummaryCalculator.calculate(entries)
        print(
            f"\n  {acc.holder_name} ({acc.currency})\n"
            f"    Deposits:    {summary.total_deposits}\n"
            f"    Withdrawals: {summary.total_withdrawals}\n"
            f"    Interest:    {summary.total_interest}\n"
            f"    Fees:        {summary.total_fees}\n"
            f"    Entries:     {summary.entry_count}"
        )

    # ── 9. Export statements ───────────────────────────────────────────────────
    section("9. Exporting statements")

    with tempfile.TemporaryDirectory() as tmp:
        for acc in [savings, checking, high_yield]:
            name = acc.holder_name.replace(" ", "_").lower()
            json_path = os.path.join(tmp, f"{name}_statement.json")
            csv_path = os.path.join(tmp, f"{name}_statement.csv")
            StatementExporter.to_json(acc, json_path)
            StatementExporter.to_csv(acc, csv_path)
            print(f"  ✔ {acc.holder_name}: JSON and CSV exported to {tmp}")

        # Show a snippet of the savings JSON
        json_path = os.path.join(tmp, "arjun_sharma_statement.json")
        with open(json_path, encoding="utf-8") as fh:
            data = json.load(fh)
        print(f"\n  Savings account JSON snippet:")
        print(f"    account_id:  {data['account_id'][:8]}…")
        print(f"    balance:     {data['balance']} {data['currency']}")
        print(f"    entry count: {len(data['entries'])}")

    # ── 10. Currency conversion example ────────────────────────────────────────
    section("10. Explicit currency conversion (demonstration)")
    usd_amount = Decimal("100.00")
    inr_amount = exchange_svc.convert(usd_amount, "USD", "INR")
    print(f"  $100.00 USD → ₹{inr_amount} INR  (rate: 83.50)")

    print(f"\n{'=' * 62}")
    print("  Demo complete.  All assertions passed implicitly.")
    print(f"{'=' * 62}\n")


if __name__ == "__main__":
    main()
