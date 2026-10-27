"""What a purchase costs and how the price splits into the amount and the VAT."""

from __future__ import annotations

import pytest

from app.bss_money.domain.purchase import split_vat


@pytest.mark.parametrize(
    ("price", "rate", "net", "vat"),
    [
        (107_500, 750, 100_000, 7_500),  # a price that divides exactly
        (100_000, 750, 93_023, 6_977),  # one that does not: the VAT rounds, the net is the rest
        (0, 750, 0, 0),
        (1, 750, 1, 0),  # too small to carry a kobo of VAT
        (14, 750, 13, 1),  # 1.0465 rounds to 1
        (100_000, 0, 100_000, 0),  # no VAT
        (100_000, 10_000, 50_000, 50_000),  # 100%: half the price
        (
            5_000_000_000_000,
            750,
            4_651_162_790_698,
            348_837_209_302,
        ),  # a big price, still whole kobo
    ],
)
def test_the_split_of_known_prices(price: int, rate: int, net: int, vat: int) -> None:
    assert split_vat(price, rate) == (net, vat)


def test_the_two_parts_always_add_up_to_the_price() -> None:
    for rate in (0, 1, 500, 750, 1_000, 7_777, 10_000):
        for price in [*range(3_000), 99_999, 100_001, 123_456_789]:
            net, vat = split_vat(price, rate)
            assert net + vat == price
            assert net >= 0
            assert vat >= 0


def test_the_vat_never_exceeds_what_the_rate_allows() -> None:
    for price in range(0, 5_000):
        _, vat = split_vat(price, 750)
        assert vat * 10_750 <= price * 750 + 5_375  # at most half a kobo of rounding up


@pytest.mark.parametrize(
    ("price", "rate"),
    [
        (-1, 750),
        (100, -1),
        (100, 10_001),
        (1.5, 750),
        (100, 7.5),
        (True, 750),
        (100, True),
        ("100", 750),
    ],
)
def test_nonsense_is_refused(price: object, rate: object) -> None:
    with pytest.raises(ValueError):
        split_vat(price, rate)  # type: ignore[arg-type]
