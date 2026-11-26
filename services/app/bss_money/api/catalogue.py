"""The catalogue an admin keeps in RatelDesk (docs/catalogue.md).

Staff session routes. Reading is for every signed-in staff member (the Sell SIM screen needs the
plans); changing needs `manage_catalogue`, which only admins hold. Every change is audited with the
staff member's address and the reason they gave.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Path, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from app.bss_lines.api.deps import require
from app.bss_lines.domain.staff import Permission
from app.bss_lines.repositories.desk_ports import StaffRecord
from app.bss_money.domain.catalogue import (
    CHANNELS,
    PRESETS_MAX,
    CatalogueInvalid,
    CatalogueSettings,
)
from app.bss_money.domain.purchase import OfferKind
from app.bss_money.repositories.ports import AuditRow, CatalogueScope, OfferView
from app.bss_money.services import catalogue
from app.config import Settings
from common.errors import ApiError
from common.timeutil import to_epoch

router = APIRouter(prefix="/v1/catalogue")

Reader = Annotated[StaffRecord, Depends(require(Permission.READ))]
Admin = Annotated[StaffRecord, Depends(require(Permission.MANAGE_CATALOGUE))]
RequiredKey = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=100)]
# Retiring and saving settings are idempotent by nature: the header is accepted, not needed.
OptionalKey = Annotated[str | None, Header(alias="Idempotency-Key", min_length=1, max_length=100)]
Channel = Literal["desk", "pay", "sms", "ussd"]
assert set(CHANNELS) == {"desk", "pay", "sms", "ussd"}


class OfferOut(BaseModel):
    kind: OfferKind
    offer_id: int
    name: str
    price_kobo: int
    data_bytes: int
    validity_days: int
    channels: list[str]
    state: str
    speed_dl_mbps: float | None
    speed_ul_mbps: float | None
    on_exhaustion: str | None
    slow_dl_mbps: float | None
    slow_ul_mbps: float | None


class SettingsBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    airtime_min_kobo: int = Field(ge=1)
    card_min_kobo: int = Field(ge=1)
    card_max_kobo: int = Field(ge=1)
    airtime_presets_kobo: list[int] = Field(min_length=1, max_length=PRESETS_MAX)
    voice_onnet_kobo_per_min: int = Field(ge=0)
    voice_offnet_kobo_per_min: int = Field(ge=0)
    sms_onnet_kobo: int = Field(ge=0)


class GatewayLimits(BaseModel):
    min_kobo: int
    max_kobo: int


class CatalogueOut(BaseModel):
    offers: list[OfferOut]
    settings: SettingsBody
    gateway: GatewayLimits
    channels: list[str]


class NewOfferIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: OfferKind
    name: str = Field(min_length=1, max_length=80)
    price_kobo: int = Field(ge=0)
    data_bytes: int = Field(ge=1)
    validity_days: int = Field(ge=1, le=3650)
    channels: list[Channel] = Field(min_length=1)
    speed_dl_mbps: float | None = Field(default=None, gt=0)
    speed_ul_mbps: float | None = Field(default=None, gt=0)
    on_exhaustion: Literal["slow", "stop"] | None = None
    slow_dl_mbps: float | None = Field(default=None, gt=0)
    slow_ul_mbps: float | None = Field(default=None, gt=0)
    reason: str = Field(min_length=1, max_length=200)


class CreatedOut(BaseModel):
    offer_id: int
    replayed: bool


class ReasonIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=200)


class RetiredOut(BaseModel):
    retired: bool


class SettingsIn(SettingsBody):
    reason: str = Field(min_length=1, max_length=200)


class AuditOut(BaseModel):
    audit_id: int
    actor: str
    action: str
    offer_kind: str | None
    offer_id: int | None
    reason: str
    detail: str
    at: int | None


class AuditPage(BaseModel):
    items: list[AuditOut]


def _scope(request: Request) -> CatalogueScope:
    scope: CatalogueScope = request.app.state.catalogue_scope
    return scope


def _offer(o: OfferView) -> OfferOut:
    return OfferOut(
        kind=o.kind,
        offer_id=o.offer_id,
        name=o.name,
        price_kobo=o.price_kobo,
        data_bytes=o.data_bytes,
        validity_days=o.validity_days,
        channels=o.channels,
        state=o.state,
        speed_dl_mbps=o.speed_dl_mbps,
        speed_ul_mbps=o.speed_ul_mbps,
        on_exhaustion=o.on_exhaustion,
        slow_dl_mbps=o.slow_dl_mbps,
        slow_ul_mbps=o.slow_ul_mbps,
    )


def _settings_out(s: CatalogueSettings) -> SettingsBody:
    return SettingsBody(
        airtime_min_kobo=s.airtime_min_kobo,
        card_min_kobo=s.card_min_kobo,
        card_max_kobo=s.card_max_kobo,
        airtime_presets_kobo=list(s.airtime_presets_kobo),
        voice_onnet_kobo_per_min=s.voice_onnet_kobo_per_min,
        voice_offnet_kobo_per_min=s.voice_offnet_kobo_per_min,
        sms_onnet_kobo=s.sms_onnet_kobo,
    )


def _invalid(exc: CatalogueInvalid) -> ApiError:
    return ApiError(422, "invalid_catalogue", str(exc))


@router.get("", response_model=CatalogueOut)
def get_catalogue(request: Request, _staff: Reader) -> CatalogueOut:
    """Every plan and bundle (on sale and retired) and the airtime and call settings."""
    settings: Settings = request.app.state.settings
    result = catalogue.view(_scope(request))
    return CatalogueOut(
        offers=[_offer(o) for o in result.offers],
        settings=_settings_out(result.settings),
        gateway=GatewayLimits(
            min_kobo=settings.payment_min_kobo, max_kobo=settings.payment_max_kobo
        ),
        channels=list(CHANNELS),
    )


@router.post("/offers", response_model=CreatedOut)
def create_offer(
    request: Request, response: Response, body: NewOfferIn, staff: Admin, key: RequiredKey
) -> CreatedOut:
    """Publish a new plan or bundle, on sale at once."""
    try:
        created = catalogue.create_offer(
            _scope(request),
            actor=staff.email,
            offer=catalogue.OfferInput(
                kind=body.kind,
                name=body.name,
                price_kobo=body.price_kobo,
                data_bytes=body.data_bytes,
                validity_days=body.validity_days,
                channels=list(body.channels),
                speed_dl_mbps=body.speed_dl_mbps,
                speed_ul_mbps=body.speed_ul_mbps,
                on_exhaustion=body.on_exhaustion,
                slow_dl_mbps=body.slow_dl_mbps,
                slow_ul_mbps=body.slow_ul_mbps,
            ),
            reason=body.reason,
            idempotency_key=key,
        )
    except CatalogueInvalid as exc:
        raise _invalid(exc) from None
    except catalogue.KeyReused:
        raise ApiError(
            409, "conflict", "This Idempotency-Key was used for a different change."
        ) from None
    response.status_code = 200 if created.replayed else 201
    return CreatedOut(offer_id=created.offer_id, replayed=created.replayed)


@router.post("/offers/{kind}/{offer_id}/retire", response_model=RetiredOut)
def retire_offer(
    request: Request,
    kind: OfferKind,
    offer_id: Annotated[int, Path(ge=1)],
    body: ReasonIn,
    staff: Admin,
    _key: OptionalKey = None,
) -> RetiredOut:
    """Take an offer off sale. What customers already bought stands."""
    try:
        retired = catalogue.retire_offer(
            _scope(request), actor=staff.email, kind=kind, offer_id=offer_id, reason=body.reason
        )
    except CatalogueInvalid as exc:
        raise _invalid(exc) from None
    except catalogue.OfferNotFound:
        raise ApiError(404, "not_found", "No such plan or bundle.") from None
    return RetiredOut(retired=retired)


@router.put("/settings", response_model=SettingsBody)
def put_settings(
    request: Request, body: SettingsIn, staff: Admin, _key: OptionalKey = None
) -> SettingsBody:
    """Save the airtime limits and the call rates."""
    settings: Settings = request.app.state.settings
    try:
        saved = catalogue.update_settings(
            _scope(request),
            actor=staff.email,
            settings=CatalogueSettings(
                airtime_min_kobo=body.airtime_min_kobo,
                card_min_kobo=body.card_min_kobo,
                card_max_kobo=body.card_max_kobo,
                airtime_presets_kobo=tuple(body.airtime_presets_kobo),
                voice_onnet_kobo_per_min=body.voice_onnet_kobo_per_min,
                voice_offnet_kobo_per_min=body.voice_offnet_kobo_per_min,
                sms_onnet_kobo=body.sms_onnet_kobo,
            ),
            reason=body.reason,
            gateway_min_kobo=settings.payment_min_kobo,
            gateway_max_kobo=settings.payment_max_kobo,
        )
    except CatalogueInvalid as exc:
        raise _invalid(exc) from None
    return _settings_out(saved)


@router.get("/audit", response_model=AuditPage)
def get_audit(
    request: Request,
    _staff: Reader,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    before: Annotated[int | None, Query(ge=1)] = None,
) -> AuditPage:
    """Catalogue changes, newest first."""
    rows = catalogue.audit(_scope(request), limit=limit, before_id=before)
    return AuditPage(items=[_audit(r) for r in rows])


def _audit(r: AuditRow) -> AuditOut:
    return AuditOut(
        audit_id=r.audit_id,
        actor=r.actor,
        action=r.action,
        offer_kind=r.offer_kind,
        offer_id=r.offer_id,
        reason=r.reason,
        detail=r.detail,
        at=None if r.created_at is None else to_epoch(r.created_at),
    )
