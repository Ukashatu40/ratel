// The voucher operations as the contract has them (contracts/openapi.yaml, snake_case), mapped to the screen's types.
import type { BatchState, VoucherBatch, VoucherBatches, VoucherCard, VoucherState } from "./types";

export interface WireBatch {
  batch_id: number; name: string; face_value_kobo: number; card_count: number; cards_used: number; state: BatchState;
  requested_by: string; requested_at: number | null; approved_by: string | null; printed_by: string | null; printed_at: number | null;
}
export interface WireBatches { items: WireBatch[]; voucher_values_kobo: number[]; max_cards: number }
export interface WireCard {
  voucher_id: number; card_number_last4: string; batch: string; face_value_kobo: number; state: VoucherState;
  failed_attempts: number; max_attempts: number; used_by_msisdn: string | null; used_at: number | null;
}

export const batchFromWire = (b: WireBatch): VoucherBatch => ({
  batchId: b.batch_id, name: b.name, faceValueKobo: b.face_value_kobo, cardCount: b.card_count, cardsUsed: b.cards_used, state: b.state,
  requestedBy: b.requested_by, requestedAt: b.requested_at, approvedBy: b.approved_by, printedBy: b.printed_by, printedAt: b.printed_at,
});
export const batchesFromWire = (w: WireBatches): VoucherBatches => ({
  items: w.items.map(batchFromWire), voucherValuesKobo: w.voucher_values_kobo, maxCards: w.max_cards,
});
export const cardFromWire = (c: WireCard): VoucherCard => ({
  voucherId: c.voucher_id, last4: c.card_number_last4, batch: c.batch, faceValueKobo: c.face_value_kobo, state: c.state,
  failedAttempts: c.failed_attempts, maxAttempts: c.max_attempts, usedByMsisdn: c.used_by_msisdn, usedAt: c.used_at,
});
