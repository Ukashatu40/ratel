#!/usr/bin/env python3
"""Try the Paystack adapter against Paystack's real TEST mode, from a developer's machine.

    read -rs -p "Paystack TEST secret key: " PAYSTACK_SECRET_KEY; echo; export PAYSTACK_SECRET_KEY
    PYTHONPATH=services .venv/bin/python scripts/paystack_sandbox_check.py

What it does: starts a 200 naira test payment, prints the checkout page for you to open and pay
with one of the test cards Paystack shows in test mode, then asks Paystack what became of it, the
same way the app does, until it is complete. It checks the amount, the currency and the status word
against what the adapter expects, and says PASS or FAIL for each.

Safety: it refuses any key that does not start with `sk_test_`, so it can never touch live money. It
never prints the key. It talks only to Paystack. Nothing is stored. The checkout address is printed
to your terminal on purpose (you need it); do not paste it into a ticket or chat.

Exit 0: every check passed. Exit 1: a check failed (the adapter and Paystack disagree: fix
`services/app/bss_money/gateways/paystack.py`). Exit 2: it could not run (no test key).
"""

from __future__ import annotations

import os
import sys
import time

from app.bss_money.domain.payments import GatewayError, Outcome, new_provider_ref
from app.bss_money.gateways.paystack import PaystackGateway

AMOUNT_KOBO = 20_000  # 200 naira
POLL_SECONDS = 5
GIVE_UP_AFTER = 300


def say(text: str = "") -> None:
    sys.stdout.write(text + "\n")
    sys.stdout.flush()


def main() -> int:
    key = os.environ.get("PAYSTACK_SECRET_KEY", "").strip()
    if not key.startswith("sk_test_"):
        sys.stderr.write("Set PAYSTACK_SECRET_KEY to a Paystack TEST secret key (sk_test_...).\n")
        return 2
    gateway = PaystackGateway(
        key, base_url=os.environ.get("PAYSTACK_BASE_URL", "https://api.paystack.co")
    )
    failures = 0

    def check(name: str, ok: bool, detail: str = "") -> None:
        nonlocal failures
        failures += 0 if ok else 1
        say(f"  {'PASS' if ok else 'FAIL'}  {name}{'  (' + detail + ')' if detail else ''}")

    reference = new_provider_ref()
    say("1. Start a payment")
    try:
        checkout = gateway.initialize(
            amount_kobo=AMOUNT_KOBO,
            reference=reference,
            email=os.environ.get("PAYSTACK_CHECK_EMAIL", "sandbox-check@example.com"),
            callback_url=os.environ.get("PAYSTACK_CHECK_CALLBACK", "https://example.com/"),
        )
    except GatewayError as exc:
        check("Paystack accepted the initialize call", False, str(exc))
        return 1
    check("Paystack accepted the initialize call and gave an https checkout page", True)

    say("2. Ask about it before paying")
    try:
        before = gateway.verify(reference)
    except GatewayError as exc:
        check("Paystack answered the verify call", False, str(exc))
        return 1
    check(
        "a payment not yet made is pending, never a success",
        before.outcome is Outcome.PENDING,
        f"outcome={before.outcome.value}",
    )

    say()
    say("3. Pay it now, in test mode, with a test card Paystack shows on this page:")
    say(f"     {checkout.url}")
    say(f"   (waiting up to {GIVE_UP_AFTER // 60} minutes, asking Paystack every {POLL_SECONDS}s)")
    outcome = before
    deadline = time.monotonic() + GIVE_UP_AFTER
    while time.monotonic() < deadline:
        time.sleep(POLL_SECONDS)
        try:
            outcome = gateway.verify(reference)
        except GatewayError as exc:
            check("Paystack answered the verify call", False, str(exc))
            return 1
        if outcome.outcome is not Outcome.PENDING:
            break
    say()
    say("4. What Paystack says now")
    check(
        "the payment completed",
        outcome.outcome is Outcome.SUCCESS,
        f"outcome={outcome.outcome.value}",
    )
    check(
        f"the amount is {AMOUNT_KOBO} kobo, as an integer",
        outcome.amount_kobo == AMOUNT_KOBO,
        f"amount={outcome.amount_kobo}",
    )
    check(
        "the currency is NGN", outcome.currency == "NGN", f"currency={outcome.currency or 'none'}"
    )
    check("there is a transaction id", bool(outcome.provider_txn_id))
    say()
    say(
        "PASS: the adapter agrees with Paystack."
        if failures == 0
        else f"FAIL: {failures} check(s) disagree."
    )
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
