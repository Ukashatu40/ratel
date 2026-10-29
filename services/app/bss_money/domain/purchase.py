"""What a customer pays for a plan or a bundle, and how the payment is split in the ledger.

Pure: no database, no clock, no logging. Money is whole kobo, never a float.

The rules (Build Plan, RatelBSS: money; PRODUCT_RULES.md, Wallet and plan rules):
- The wallet pays for plans and bundles. Each purchase creates one allowance bucket.
- VAT is recorded as **its own ledger entry**, so reports can separate it. The rate is finance's to
  confirm (7.5% at the time of the Build Plan, decision 7).

TODO(finance, PRD): whether an offer's `price_kobo` already includes VAT. It is taken to be the
whole price the customer pays, VAT included, which is how retail prices are usually shown; the
customer's wallet drops by exactly `price_kobo`, and the two ledger entries add up to it. If finance
says the price is before VAT, only `split_vat` and its callers change.
"""

from __future__ import annotations

from enum import StrEnum

BASIS_POINTS = 10_000
DEFAULT_VAT_BASIS_POINTS = 750  # 7.5%


class OfferKind(StrEnum):
    PLAN = "plan"
    BUNDLE = "bundle"


def split_vat(price_kobo: int, rate_bps: int) -> tuple[int, int]:
    """(net, vat) of a price that includes VAT at `rate_bps` basis points. They add up to the price.

    The VAT is rounded half up to a whole kobo, and the net is whatever is left, so a purchase never
    gains or loses a kobo to rounding.
    """
    _require_whole(price_kobo, "price_kobo")
    _require_whole(rate_bps, "rate_bps")
    if price_kobo < 0:
        raise ValueError("price_kobo cannot be negative")
    if not 0 <= rate_bps <= BASIS_POINTS:
        raise ValueError("rate_bps must be between 0 and 10000")
    denominator = BASIS_POINTS + rate_bps
    vat = (price_kobo * rate_bps + denominator // 2) // denominator
    return price_kobo - vat, vat


def _require_whole(value: object, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be a whole number")
