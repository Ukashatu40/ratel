"""Voucher batches managed in RatelDesk: the steps a batch moves through.

See docs/runbooks/voucher-batches.md.

Pure: no database, no clock, no logging. Decided by the project lead on 2026-11-27:
- An admin requests a batch: a face value from the catalogue's list and a number of cards.
- An admin approves it (for now the same admin may: every step records who did it).
- Printing makes the cards and their PINs, once, as a PDF; the cards are then `sent_to_printer`.
  PINs exist only in that PDF. No card or PIN exists before approval.
- Then `in_stock`, then `on_sale`, when the cards can be redeemed.
- A whole batch can be locked at any step (lost in transit, a print that never arrived): its
  cards that are not used become `locked` and can never be redeemed.
- Cards do not expire.
"""

from __future__ import annotations

from enum import StrEnum

# Printing hashes every PIN (about 40 ms each) while the request waits, so a batch stays small
# enough to print well inside the 30 seconds the reverse proxy allows: 10 pages of 24 cards.
MAX_DESK_BATCH = 240


class BatchState(StrEnum):
    REQUESTED = "requested"
    APPROVED = "approved"
    SENT_TO_PRINTER = "sent_to_printer"
    IN_STOCK = "in_stock"
    ON_SALE = "on_sale"
    LOCKED = "locked"


B = BatchState
# The step an admin takes from each state with "advance". Printing (approved -> sent_to_printer)
# is its own action, as it makes the cards.
ADVANCE: dict[BatchState, BatchState] = {
    B.REQUESTED: B.APPROVED,
    B.SENT_TO_PRINTER: B.IN_STOCK,
    B.IN_STOCK: B.ON_SALE,
}


class BatchStepRefused(ValueError):
    """The batch cannot take this step from where it is."""


def check_advance(current: BatchState, target: BatchState) -> None:
    if ADVANCE.get(current) != target:
        raise BatchStepRefused(f"a batch that is {current.value} cannot move to {target.value}")


def check_print(current: BatchState) -> None:
    if current is not B.APPROVED:
        raise BatchStepRefused(
            "only an approved batch can be printed, and only once"
            if current is not B.SENT_TO_PRINTER
            else "this batch has been printed already; lock it and request a new one if the "
            "sheet was lost"
        )


def check_lock(current: BatchState) -> None:
    if current is B.LOCKED:
        raise BatchStepRefused("the batch is locked already")


def batch_name(batch_id: int) -> str:
    """The name printed on every card of the batch: V-00007."""
    return f"V-{batch_id:05d}"


def check_request(face_value_kobo: int, card_count: int, values: tuple[int, ...]) -> None:
    if face_value_kobo not in values:
        raise BatchStepRefused("the face value must be one of the voucher values in the catalogue")
    if not 1 <= card_count <= MAX_DESK_BATCH:
        raise BatchStepRefused(f"a batch has between 1 and {MAX_DESK_BATCH} cards")
