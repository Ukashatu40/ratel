"""The welcome SMS text (docs/welcome-sms.md)."""

from __future__ import annotations

import pytest

from app.bss_lines.domain.welcome import SMS_LIMIT, national_number, welcome_text


def test_the_text_names_the_number_as_customers_dial_it_and_fits_one_sms() -> None:
    text = welcome_text("2348000010010")
    assert text == (
        "Welcome to Ratelplus! Your number is 08000010010. "
        "Text MENU to 647 for balance, bundles and top-up."
    )
    assert len(text) <= SMS_LIMIT
    assert text.isascii()  # the GSM 7-bit alphabet holds every character here


@pytest.mark.parametrize("bad", ["08000010010", "234800001001", "+2348000010010", ""])
def test_a_number_not_in_234_form_is_refused(bad: str) -> None:
    with pytest.raises(ValueError):
        national_number(bad)
