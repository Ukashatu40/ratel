"""The catalogue an admin keeps in RatelDesk: offers on sale and the airtime and call settings.

Pure: no database, no clock, no logging. Money is whole kobo, data whole bytes, time whole days.

Decided by the project lead on 2026-11-24 (docs/catalogue.md):
- Prices, bundles and plans are set by an admin in RatelDesk, never in code or SQL.
- An offer that has been sold is never edited: it is retired and a new one is published, so what a
  customer bought keeps the terms it was bought with.
- Airtime: the smallest top-up is 20 naira where no payment processor imposes more; card payments
  keep the gateway's floor (100 naira at Paystack). Voice calls are charged from airtime, per
  second, at one rate for calls to Ratelplus numbers (on-net) and one for every other number.
- An SMS to another Ratelplus line costs one price, VAT inclusive (2026-11-26: N2). Texts to 555
  are free; texts to other networks are refused until there is SMS interconnect (ADR 0013).
- Voucher batches made in RatelDesk have one of a fixed list of face values, kept here (2026-11-27).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

# Where an offer may be sold. Stored comma-separated in the offer's `channels` column.
CHANNELS = ("desk", "pay", "sms", "ussd")
NAME_MAX_LENGTH = 80
REASON_MAX_LENGTH = 200
PRESETS_MAX = 6
VOUCHER_VALUES_MAX = 8
KOBO_PER_NAIRA = 100
# N100, N200, N500, N1,000 and N2,000 until an admin changes them
DEFAULT_VOUCHER_VALUES_KOBO = (10_000, 20_000, 50_000, 100_000, 200_000)


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


class CatalogueInvalid(ValueError):
    """A catalogue change that breaks a rule. The message says which, in words staff can read."""


class CatalogueAction(StrEnum):
    """What a catalogue audit row records."""

    CREATE_BUNDLE = "create_bundle"
    CREATE_PLAN = "create_plan"
    RETIRE_BUNDLE = "retire_bundle"
    RETIRE_PLAN = "retire_plan"
    UPDATE_SETTINGS = "update_settings"


@dataclass(frozen=True)
class CatalogueSettings:
    """Airtime limits and call rates. One set for the whole network."""

    airtime_min_kobo: int  # the smallest top-up where no processor sets a floor
    card_min_kobo: int  # the smallest card payment (never below the deployment's floor)
    card_max_kobo: int
    airtime_presets_kobo: tuple[int, ...]  # the amounts the SMS and USSD menus offer
    voice_onnet_kobo_per_min: int  # to a Ratelplus number
    voice_offnet_kobo_per_min: int  # to any other number
    sms_onnet_kobo: int  # one SMS to a Ratelplus number, VAT inclusive
    voucher_values_kobo: tuple[int, ...]  # the face values a voucher batch may have

    def __post_init__(self) -> None:
        for name in (
            "airtime_min_kobo",
            "card_min_kobo",
            "card_max_kobo",
            "voice_onnet_kobo_per_min",
            "voice_offnet_kobo_per_min",
            "sms_onnet_kobo",
        ):
            value = getattr(self, name)
            if not _is_int(value) or value < 0:
                raise CatalogueInvalid(f"{name} must be a whole number of kobo, zero or more")
        if self.airtime_min_kobo < 1:
            raise CatalogueInvalid("the smallest top-up must be at least 1 kobo")
        if self.card_min_kobo < self.airtime_min_kobo:
            raise CatalogueInvalid("the smallest card payment cannot be below the smallest top-up")
        if self.card_max_kobo < self.card_min_kobo:
            raise CatalogueInvalid("the largest card payment cannot be below the smallest")
        presets = self.airtime_presets_kobo
        if not isinstance(presets, tuple) or not 1 <= len(presets) <= PRESETS_MAX:
            raise CatalogueInvalid(f"give between 1 and {PRESETS_MAX} airtime amounts")
        if any(not _is_int(p) for p in presets) or list(presets) != sorted(set(presets)):
            raise CatalogueInvalid("airtime amounts must be whole kobo, different, smallest first")
        if presets[0] < self.card_min_kobo or presets[-1] > self.card_max_kobo:
            raise CatalogueInvalid("every airtime amount must be within the card payment limits")
        values = self.voucher_values_kobo
        if not isinstance(values, tuple) or not 1 <= len(values) <= VOUCHER_VALUES_MAX:
            raise CatalogueInvalid(f"give between 1 and {VOUCHER_VALUES_MAX} voucher values")
        if any(not _is_int(v) for v in values) or list(values) != sorted(set(values)):
            raise CatalogueInvalid("voucher values must be whole kobo, different, smallest first")
        if values[0] < self.airtime_min_kobo or values[-1] > self.card_max_kobo:
            raise CatalogueInvalid(
                "every voucher value must be between the smallest top-up and the largest card "
                "payment"
            )


# Until an admin saves settings. The call rates are the project lead's starting values of
# 2026-11-24, the SMS price of 2026-11-26; all are meant to be changed in RatelDesk.
DEFAULT_SETTINGS = CatalogueSettings(
    airtime_min_kobo=20 * KOBO_PER_NAIRA,
    card_min_kobo=100 * KOBO_PER_NAIRA,
    card_max_kobo=1_000_000 * KOBO_PER_NAIRA,
    airtime_presets_kobo=(10_000, 20_000, 50_000, 100_000),
    voice_onnet_kobo_per_min=10 * KOBO_PER_NAIRA,
    voice_offnet_kobo_per_min=20 * KOBO_PER_NAIRA,
    sms_onnet_kobo=2 * KOBO_PER_NAIRA,
    voucher_values_kobo=DEFAULT_VOUCHER_VALUES_KOBO,
)


def channels_from_list(channels: list[str] | tuple[str, ...]) -> str:
    """The stored form of an offer's channels, after checking each one."""
    wanted = list(dict.fromkeys(channels))  # keeps order, drops repeats
    if not wanted:
        raise CatalogueInvalid("choose at least one channel")
    unknown = [c for c in wanted if c not in CHANNELS]
    if unknown:
        raise CatalogueInvalid(f"unknown channel: {', '.join(unknown)}")
    return ",".join(c for c in CHANNELS if c in wanted)


def channels_to_list(stored: str) -> list[str]:
    """Stored channels as a list. Older rows may hold names from before this module; kept as is."""
    return [c for c in (part.strip() for part in stored.split(",")) if c]


def check_name(name: str) -> str:
    value = " ".join(name.split()) if isinstance(name, str) else ""
    if not value:
        raise CatalogueInvalid("the name must not be empty")
    if len(value) > NAME_MAX_LENGTH:
        raise CatalogueInvalid(f"the name is longer than {NAME_MAX_LENGTH} characters")
    return value


def check_reason(reason: str) -> str:
    value = " ".join(reason.split()) if isinstance(reason, str) else ""
    if not value:
        raise CatalogueInvalid("say why")
    if len(value) > REASON_MAX_LENGTH:
        raise CatalogueInvalid(f"the reason is longer than {REASON_MAX_LENGTH} characters")
    return value
