"""Keeping the catalogue: offers on sale and the airtime and call settings (docs/catalogue.md).

Every change is written to `catalogue_audit` in the same transaction, with who made it and why.
A sold offer is never edited: it is retired and a new one is created. Creating is idempotent on the
caller's Idempotency-Key; retiring an offer that is already retired changes nothing.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.bss_money.domain.catalogue import (
    DEFAULT_SETTINGS,
    CatalogueAction,
    CatalogueInvalid,
    CatalogueSettings,
    channels_from_list,
    check_name,
    check_reason,
)
from app.bss_money.domain.plans import Bundle, OnExhaustion, Plan
from app.bss_money.domain.purchase import OfferKind
from app.bss_money.repositories.ports import (
    AuditRow,
    CatalogueRepository,
    CatalogueScope,
    NewOffer,
    OfferView,
)
from common.logging import log_event

log = logging.getLogger("ratel.bss.money.catalogue")

ON_SALE = "on_sale"
RETIRED = "retired"


class OfferNotFound(Exception):
    pass


class KeyReused(Exception):
    """The Idempotency-Key was used for a different change."""


@dataclass(frozen=True)
class OfferInput:
    """What an admin types to create an offer. Speeds and slow-down are for plans only."""

    kind: OfferKind
    name: str
    price_kobo: int
    data_bytes: int
    validity_days: int
    channels: list[str]
    speed_dl_mbps: float | None = None
    speed_ul_mbps: float | None = None
    on_exhaustion: str | None = None
    slow_dl_mbps: float | None = None
    slow_ul_mbps: float | None = None


@dataclass(frozen=True)
class Created:
    offer_id: int
    replayed: bool


@dataclass(frozen=True)
class Catalogue:
    offers: list[OfferView]
    settings: CatalogueSettings


def settings_or_default(repository: CatalogueRepository) -> CatalogueSettings:
    return repository.settings() or DEFAULT_SETTINGS


def card_limits(scope: CatalogueScope, *, floor_kobo: int, ceiling_kobo: int) -> tuple[int, int]:
    """The card payment limits: the admin's, kept inside the deployment's gateway limits."""
    with scope() as repository:
        settings = settings_or_default(repository)
    return max(floor_kobo, settings.card_min_kobo), min(ceiling_kobo, settings.card_max_kobo)


def view(scope: CatalogueScope) -> Catalogue:
    with scope() as repository:
        return Catalogue(offers=repository.offers(), settings=settings_or_default(repository))


def audit(scope: CatalogueScope, *, limit: int, before_id: int | None) -> list[AuditRow]:
    with scope() as repository:
        return repository.audit_page(limit, before_id)


def create_offer(
    scope: CatalogueScope, *, actor: str, offer: OfferInput, reason: str, idempotency_key: str
) -> Created:
    """Check the offer as the money rules would, then store it on sale."""
    new = _checked(offer)
    why = check_reason(reason)
    action = (
        CatalogueAction.CREATE_PLAN
        if offer.kind is OfferKind.PLAN
        else CatalogueAction.CREATE_BUNDLE
    )
    with scope() as repository:
        earlier = repository.audit_for_key(idempotency_key)
        if earlier is not None:
            if earlier.action != action.value or earlier.offer_id is None:
                raise KeyReused("this Idempotency-Key was used for a different change")
            return Created(offer_id=earlier.offer_id, replayed=True)
        offer_id = repository.add_offer(new)
        repository.add_audit(
            actor=actor,
            action=action.value,
            offer_kind=offer.kind.value,
            offer_id=offer_id,
            idempotency_key=idempotency_key,
            reason=why,
            detail=describe(new),
        )
    log_event(
        log, logging.INFO, "catalogue.offer_created", kind=offer.kind.value, offer_id=offer_id
    )
    return Created(offer_id=offer_id, replayed=False)


def retire_offer(
    scope: CatalogueScope, *, actor: str, kind: OfferKind, offer_id: int, reason: str
) -> bool:
    """Take the offer off sale. True if it was on sale, False if it was already retired.

    What customers already bought stands: their buckets keep the terms they paid for.
    """
    why = check_reason(reason)
    with scope() as repository:
        state = repository.lock_offer_state(kind, offer_id)
        if state is None:
            raise OfferNotFound("no such offer")
        if state == RETIRED:
            return False
        repository.retire(kind, offer_id)
        action = (
            CatalogueAction.RETIRE_PLAN if kind is OfferKind.PLAN else CatalogueAction.RETIRE_BUNDLE
        )
        repository.add_audit(
            actor=actor,
            action=action.value,
            offer_kind=kind.value,
            offer_id=offer_id,
            idempotency_key=None,
            reason=why,
            detail=f"was {state}",
        )
    log_event(log, logging.INFO, "catalogue.offer_retired", kind=kind.value, offer_id=offer_id)
    return True


def update_settings(
    scope: CatalogueScope,
    *,
    actor: str,
    settings: CatalogueSettings,
    reason: str,
    gateway_min_kobo: int,
    gateway_max_kobo: int,
) -> CatalogueSettings:
    """Save the settings. Card limits must stay inside what the deployment allows the gateway."""
    why = check_reason(reason)
    if settings.card_min_kobo < gateway_min_kobo:
        raise CatalogueInvalid(
            f"the payment gateway takes no less than {gateway_min_kobo / 100:,.2f} naira"
        )
    if settings.card_max_kobo > gateway_max_kobo:
        raise CatalogueInvalid(
            f"the payment gateway takes no more than {gateway_max_kobo / 100:,.2f} naira"
        )
    with scope() as repository:
        before = settings_or_default(repository)
        if before == settings:
            return before
        repository.save_settings(settings)
        repository.add_audit(
            actor=actor,
            action=CatalogueAction.UPDATE_SETTINGS.value,
            offer_kind=None,
            offer_id=None,
            idempotency_key=None,
            reason=why,
            detail=_settings_change(before, settings),
        )
    log_event(log, logging.INFO, "catalogue.settings_updated")
    return settings


def describe(offer: NewOffer) -> str:
    parts = [
        offer.name,
        f"{offer.price_kobo / 100:,.2f} naira",
        _size(offer.data_bytes),
        f"{offer.validity_days} day{'s' if offer.validity_days != 1 else ''}",
        offer.channels,
    ]
    if offer.kind is OfferKind.PLAN:
        parts.append(f"{offer.speed_dl_mbps}/{offer.speed_ul_mbps} Mbps")
        if offer.on_exhaustion == OnExhaustion.SLOW.value:
            parts.append(f"then {offer.slow_dl_mbps}/{offer.slow_ul_mbps} Mbps")
        else:
            parts.append("then data stops")
    return ", ".join(parts)


def _size(data_bytes: int) -> str:
    if data_bytes >= 1_000_000_000:
        return f"{data_bytes / 1_000_000_000:g} GB"
    return f"{data_bytes / 1_000_000:g} MB"


def _settings_change(before: CatalogueSettings, after: CatalogueSettings) -> str:
    changed = []
    for name in (
        "airtime_min_kobo",
        "card_min_kobo",
        "card_max_kobo",
        "airtime_presets_kobo",
        "voice_onnet_kobo_per_min",
        "voice_offnet_kobo_per_min",
        "sms_onnet_kobo",
    ):
        old, new = getattr(before, name), getattr(after, name)
        if old != new:
            changed.append(f"{name} {old} -> {new}")
    return "; ".join(changed) or "no change"


def _checked(offer: OfferInput) -> NewOffer:
    """The offer in its stored form, or CatalogueInvalid saying what is wrong."""
    name = check_name(offer.name)
    channels = channels_from_list(offer.channels)
    try:
        if offer.kind is OfferKind.PLAN:
            if offer.speed_dl_mbps is None or offer.speed_ul_mbps is None:
                raise CatalogueInvalid("a plan needs its download and upload speeds")
            exhaustion = OnExhaustion(offer.on_exhaustion or "")
            slow = exhaustion is OnExhaustion.SLOW
            Plan(
                plan_id=1,
                name=name,
                price_kobo=offer.price_kobo,
                validity_days=offer.validity_days,
                data_bytes=offer.data_bytes,
                speed_ul_mbps=offer.speed_ul_mbps,
                speed_dl_mbps=offer.speed_dl_mbps,
                channels=tuple(channels.split(",")),
                on_exhaustion=exhaustion,
                slow_ul_mbps=offer.slow_ul_mbps if slow else None,
                slow_dl_mbps=offer.slow_dl_mbps if slow else None,
            )
            return NewOffer(
                kind=OfferKind.PLAN,
                name=name,
                price_kobo=offer.price_kobo,
                data_bytes=offer.data_bytes,
                validity_days=offer.validity_days,
                channels=channels,
                speed_dl_mbps=offer.speed_dl_mbps,
                speed_ul_mbps=offer.speed_ul_mbps,
                on_exhaustion=exhaustion.value,
                slow_dl_mbps=offer.slow_dl_mbps if slow else None,
                slow_ul_mbps=offer.slow_ul_mbps if slow else None,
            )
        Bundle(
            bundle_id=1,
            name=name,
            price_kobo=offer.price_kobo,
            validity_days=offer.validity_days,
            data_bytes=offer.data_bytes,
            channels=tuple(channels.split(",")),
        )
    except CatalogueInvalid:
        raise
    except ValueError as exc:
        raise CatalogueInvalid(str(exc).replace("_", " ")) from None
    return NewOffer(
        kind=OfferKind.BUNDLE,
        name=name,
        price_kobo=offer.price_kobo,
        data_bytes=offer.data_bytes,
        validity_days=offer.validity_days,
        channels=channels,
    )
