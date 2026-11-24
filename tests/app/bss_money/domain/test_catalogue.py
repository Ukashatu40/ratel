"""The catalogue's rules: settings, channels, names and reasons."""

from __future__ import annotations

from dataclasses import replace

import pytest

from app.bss_money.domain.catalogue import (
    DEFAULT_SETTINGS,
    CatalogueInvalid,
    channels_from_list,
    channels_to_list,
    check_name,
    check_reason,
)


def test_the_default_settings_are_the_decided_ones() -> None:
    assert DEFAULT_SETTINGS.airtime_min_kobo == 2_000  # 20 naira
    assert DEFAULT_SETTINGS.card_min_kobo == 10_000  # the gateway's 100 naira
    assert DEFAULT_SETTINGS.airtime_presets_kobo == (10_000, 20_000, 50_000, 100_000)


@pytest.mark.parametrize(
    ("change", "words"),
    [
        ({"airtime_min_kobo": 0}, "at least 1 kobo"),
        ({"card_min_kobo": 1_000}, "below the smallest top-up"),
        ({"card_max_kobo": 5_000}, "below the smallest"),
        ({"airtime_presets_kobo": ()}, "between 1 and"),
        ({"airtime_presets_kobo": (20_000, 10_000)}, "smallest first"),
        ({"airtime_presets_kobo": (10_000, 10_000)}, "different"),
        ({"airtime_presets_kobo": (5_000,)}, "within the card payment limits"),
        ({"voice_onnet_kobo_per_min": -1}, "zero or more"),
        ({"voice_offnet_kobo_per_min": 1.5}, "whole number"),
    ],
)
def test_settings_that_break_a_rule_are_refused_in_words(
    change: dict[str, object], words: str
) -> None:
    with pytest.raises(CatalogueInvalid, match=words):
        replace(DEFAULT_SETTINGS, **change)  # type: ignore[arg-type]


def test_channels_are_checked_deduplicated_and_kept_in_a_fixed_order() -> None:
    assert channels_from_list(["ussd", "desk", "ussd", "sms"]) == "desk,sms,ussd"
    assert channels_to_list("desk,sms, ussd,") == ["desk", "sms", "ussd"]
    with pytest.raises(CatalogueInvalid, match="at least one channel"):
        channels_from_list([])
    with pytest.raises(CatalogueInvalid, match="unknown channel: radio"):
        channels_from_list(["desk", "radio"])


def test_names_and_reasons_are_trimmed_and_required() -> None:
    assert check_name("  Weekly   3GB ") == "Weekly 3GB"
    assert check_reason(" new price\nlist ") == "new price list"
    with pytest.raises(CatalogueInvalid):
        check_name("   ")
    with pytest.raises(CatalogueInvalid, match="say why"):
        check_reason("")
    with pytest.raises(CatalogueInvalid, match="longer than 80"):
        check_name("x" * 81)
