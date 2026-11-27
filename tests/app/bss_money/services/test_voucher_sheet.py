"""The printed voucher sheet: a well formed PDF, 24 cards a page, every card's number and PIN."""

from __future__ import annotations

import re
from datetime import UTC, datetime

import pytest

from app.bss_money.domain.vouchers import new_card_number, new_pin
from app.bss_money.services.voucher_sheet import (
    CARDS_PER_PAGE,
    SheetBatch,
    SheetCard,
    groups,
    naira_amount,
    render,
    width,
)
from tests.app.bss_money.api.test_voucher_batches_api import sheet_cards, sheet_text

BATCH = SheetBatch("V-00042", 50_000, 30, datetime(2026, 11, 27, 13, 5, tzinfo=UTC), "a@b.test")


def _cards(n: int) -> list[SheetCard]:
    return [SheetCard(i, new_card_number(), new_pin()) for i in range(1, n + 1)]


def test_the_file_is_a_pdf_whose_cross_reference_table_is_right() -> None:
    pdf = render(BATCH, _cards(30))
    assert pdf.startswith(b"%PDF-1.4\n")
    xref_at = int(re.search(rb"startxref\n(\d+)\n%%EOF", pdf).group(1))  # type: ignore[union-attr]
    assert pdf[xref_at:].startswith(b"xref\n")
    offsets = [int(o) for o in re.findall(rb"(\d{10}) 00000 n ", pdf[xref_at:])]
    for number, offset in enumerate(offsets, start=1):
        assert pdf[offset:].startswith(f"{number} 0 obj\n".encode())


def test_24_cards_a_page_and_every_card_printed_once_in_order() -> None:
    cards = _cards(CARDS_PER_PAGE + 6)
    pdf = render(BATCH, cards)
    assert pdf.count(b"/Type /Page ") == 2
    assert sheet_cards(pdf) == [(c.card_number, c.pin) for c in cards]
    text = sheet_text(pdf)
    assert "Page 1 of 2" in text and "Page 2 of 2" in text
    assert "V-00042   No. 0030" in text


def test_the_logo_is_embedded_once_and_the_text_says_how_to_load_a_card() -> None:
    pdf = render(BATCH, _cards(2))
    assert pdf.count(b"/Subtype /Image") == 1
    text = sheet_text(pdf)
    assert "Text CARD, the card no. and PIN to 555" in text
    assert "or dial *123*card no.*PIN#" in text


def test_helpers() -> None:
    assert groups("12345678901234") == "1234 5678 9012 34"
    assert naira_amount(50_000) == "500"
    assert naira_amount(10_000_050) == "100,000.50"
    assert width("0000", "HB", 10) == pytest.approx(4 * 5.56)
    assert width("AAAA", "C", 10) == pytest.approx(24)


def test_an_empty_batch_is_refused() -> None:
    with pytest.raises(ValueError, match="no cards"):
        render(BATCH, [])
