"""Voucher batches and cards in RatelDesk (docs/runbooks/voucher-batches.md).

Staff session routes. Seeing batches and looking a card up is for every signed-in staff member
(customer care answers "my card does not work"); every change needs `manage_vouchers`, which only
admins hold. No route ever returns a PIN, except the one-time printed sheet, which is a PDF made
once per batch and never kept.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Path, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from app.bss_lines.api.deps import now_utc, require
from app.bss_lines.domain.staff import Permission
from app.bss_lines.repositories.desk_ports import StaffRecord
from app.bss_money.domain.voucher_batches import MAX_DESK_BATCH, BatchState, BatchStepRefused
from app.bss_money.domain.vouchers import InvalidVoucherTransition, is_card_number
from app.bss_money.repositories.ports import BatchView, VoucherAdminScope
from app.bss_money.services import voucher_batches
from common.errors import ApiError
from common.timeutil import to_epoch

router = APIRouter(prefix="/v1")

Reader = Annotated[StaffRecord, Depends(require(Permission.READ))]
Manager = Annotated[StaffRecord, Depends(require(Permission.MANAGE_VOUCHERS))]
RequiredKey = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=100)]
# Moving and locking are idempotent by nature: the header is accepted, not needed.
OptionalKey = Annotated[str | None, Header(alias="Idempotency-Key", min_length=1, max_length=100)]
BatchId = Annotated[int, Path(ge=1)]
Reason = Annotated[str, Field(min_length=3, max_length=200)]


class BatchOut(BaseModel):
    batch_id: int
    name: str
    face_value_kobo: int
    card_count: int
    state: str
    requested_by: str
    requested_at: int | None
    approved_by: str | None
    printed_by: str | None
    printed_at: int | None
    cards_used: int


class BatchesOut(BaseModel):
    items: list[BatchOut]
    voucher_values_kobo: list[int]
    max_cards: int


class NewBatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    face_value_kobo: int = Field(ge=1)
    card_count: int = Field(ge=1, le=MAX_DESK_BATCH)
    reason: Reason


class NewBatchOut(BaseModel):
    batch: BatchOut
    replayed: bool


class AdvanceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: Literal["approved", "in_stock", "on_sale"]
    reason: Reason


class ReasonIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: Reason


class LookupIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    card_number: str = Field(min_length=20, max_length=20, pattern=r"^[0-9]{20}$")


class CardOut(BaseModel):
    voucher_id: int
    card_number_last4: str
    batch: str
    face_value_kobo: int
    state: str
    failed_attempts: int
    max_attempts: int
    used_by_msisdn: str | None
    used_at: int | None


def _scope(request: Request) -> VoucherAdminScope:
    scope: VoucherAdminScope = request.app.state.voucher_admin_scope
    return scope


def _batch(b: BatchView) -> BatchOut:
    return BatchOut(
        batch_id=b.batch_id,
        name=b.name,
        face_value_kobo=b.face_value_kobo,
        card_count=b.card_count,
        state=b.state,
        requested_by=b.requested_by,
        requested_at=None if b.requested_at is None else to_epoch(b.requested_at),
        approved_by=b.approved_by,
        printed_by=b.printed_by,
        printed_at=None if b.printed_at is None else to_epoch(b.printed_at),
        cards_used=b.cards_used,
    )


def _refused(exc: Exception) -> ApiError:
    return ApiError(409, "voucher_step_refused", str(exc))


_NOT_FOUND = ApiError(404, "not_found", "No such voucher batch")


@router.get("/voucher-batches", response_model=BatchesOut)
def get_batches(request: Request, _staff: Reader) -> BatchesOut:
    """The latest 100 batches, newest first, with the face values a new batch may have."""
    return BatchesOut(
        items=[_batch(b) for b in voucher_batches.list_batches(_scope(request))],
        voucher_values_kobo=list(voucher_batches.voucher_values(_scope(request))),
        max_cards=MAX_DESK_BATCH,
    )


@router.post("/voucher-batches", response_model=NewBatchOut)
def post_batch(
    request: Request, response: Response, body: NewBatchIn, staff: Manager, key: RequiredKey
) -> NewBatchOut:
    """Request a batch. No card or PIN exists until it is approved and printed."""
    try:
        batch, replayed = voucher_batches.request_batch(
            _scope(request),
            actor=staff.email,
            face_value_kobo=body.face_value_kobo,
            card_count=body.card_count,
            reason=body.reason,
            idempotency_key=key,
        )
    except BatchStepRefused as exc:
        raise ApiError(422, "invalid_voucher_batch", str(exc)) from None
    response.status_code = 200 if replayed else 201
    return NewBatchOut(batch=_batch(batch), replayed=replayed)


@router.post("/voucher-batches/{batch_id}/advance", response_model=BatchOut)
def post_advance(
    request: Request, batch_id: BatchId, body: AdvanceIn, staff: Manager, _key: OptionalKey = None
) -> BatchOut:
    """Approve the batch, mark it in stock, or put it on sale (its cards can then be redeemed)."""
    try:
        batch = voucher_batches.advance_batch(
            _scope(request),
            batch_id=batch_id,
            to=BatchState(body.state),
            actor=staff.email,
            reason=body.reason,
        )
    except voucher_batches.BatchNotFound:
        raise _NOT_FOUND from None
    except (BatchStepRefused, InvalidVoucherTransition) as exc:
        raise _refused(exc) from None
    return _batch(batch)


@router.post(
    "/voucher-batches/{batch_id}/print",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
)
def post_print(
    request: Request, batch_id: BatchId, staff: Manager, _key: OptionalKey = None
) -> Response:
    """Make the cards and their PINs, and return the printable sheet. Once per batch, ever."""
    try:
        pdf = voucher_batches.print_batch(
            _scope(request), batch_id=batch_id, actor=staff.email, now=now_utc(request)
        )
    except voucher_batches.BatchNotFound:
        raise _NOT_FOUND from None
    except BatchStepRefused as exc:
        raise _refused(exc) from None
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="ratelplus-vouchers-{batch_id}.pdf"',
            "Cache-Control": "no-store",
        },
    )


@router.post("/voucher-batches/{batch_id}/lock", response_model=BatchOut)
def post_lock_batch(
    request: Request, batch_id: BatchId, body: ReasonIn, staff: Manager, _key: OptionalKey = None
) -> BatchOut:
    """Lock the batch and its cards that are not used: they can never be redeemed."""
    try:
        batch = voucher_batches.lock_batch(
            _scope(request), batch_id=batch_id, actor=staff.email, reason=body.reason
        )
    except voucher_batches.BatchNotFound:
        raise _NOT_FOUND from None
    except BatchStepRefused as exc:
        raise _refused(exc) from None
    return _batch(batch)


@router.post("/vouchers/lookup", response_model=CardOut)
def post_lookup(
    request: Request, body: LookupIn, _staff: Reader, _key: OptionalKey = None
) -> CardOut:
    """A card's state by its number (POST, so the number stays out of logs). Never its PIN."""
    if not is_card_number(body.card_number):
        raise ApiError(422, "invalid_card_number", "A card number is 20 digits")
    found = voucher_batches.lookup_card(
        _scope(request), card_number=body.card_number, now=now_utc(request)
    )
    if found is None:
        raise ApiError(404, "not_found", "No voucher with that card number")
    card = found.card
    return CardOut(
        voucher_id=card.voucher_id,
        card_number_last4=card.card_number[-4:],
        batch=card.batch,
        face_value_kobo=card.face_value_kobo,
        state=card.state.value,
        failed_attempts=found.failed_attempts,
        max_attempts=found.max_attempts,
        used_by_msisdn=card.used_by_msisdn,
        used_at=None if card.used_at is None else to_epoch(card.used_at),
    )


@router.post("/vouchers/{voucher_id}/lock", response_model=CardOut)
def post_lock_card(
    request: Request,
    voucher_id: Annotated[int, Path(ge=1)],
    body: ReasonIn,
    staff: Manager,
    _key: OptionalKey = None,
) -> CardOut:
    """Lock one card that is lost or stolen."""
    try:
        card = voucher_batches.lock_card(
            _scope(request), voucher_id=voucher_id, actor=staff.email, reason=body.reason
        )
    except LookupError:
        raise ApiError(404, "not_found", "No such card") from None
    except (BatchStepRefused, InvalidVoucherTransition) as exc:
        raise _refused(exc) from None
    return CardOut(
        voucher_id=card.voucher_id,
        card_number_last4=card.card_number[-4:],
        batch=card.batch,
        face_value_kobo=card.face_value_kobo,
        state=card.state.value,
        failed_attempts=0,
        max_attempts=0,
        used_by_msisdn=card.used_by_msisdn,
        used_at=None if card.used_at is None else to_epoch(card.used_at),
    )
