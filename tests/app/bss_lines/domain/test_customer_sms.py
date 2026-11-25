"""SMS to customers: the welcome text and the one-SMS rule (docs/customer-sms.md)."""

from __future__ import annotations

import pytest

from app.bss_lines.domain.customer_sms import SMS_LIMIT, check_text, national_number, welcome_text


def test_the_welcome_names_the_number_as_customers_dial_it_and_fits_one_sms() -> None:
    text = welcome_text("2348000010010")
    assert text == (
        "Welcome to Ratelplus! Your number is 08000010010. "
        "Text MENU to 647 for balance, bundles and top-up."
    )
    assert len(text) <= SMS_LIMIT and text.isascii()


@pytest.mark.parametrize("bad", ["08000010010", "234800001001", "+2348000010010", ""])
def test_a_number_not_in_234_form_is_refused(bad: str) -> None:
    with pytest.raises(ValueError):
        national_number(bad)


@pytest.mark.parametrize("bad", ["", "x" * 161, "Balance \u20a6500"])
def test_a_text_that_is_not_one_plain_sms_is_refused(bad: str) -> None:
    with pytest.raises(ValueError):
        check_text(bad)
