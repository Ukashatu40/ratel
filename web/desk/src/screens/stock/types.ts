export interface SimSummary { inStock: number; inUse: number; retired: number }
export interface SimBatch { batchId: string; importedAt: number; total: number; inStock: number; inUse: number; importedBy: string }
// BSS keeps ICCID, IMSI and batch only. SIM secret keys (Ki/OPc) never come through this app.
export interface SimImportRow { iccid: string; imsi: string; batch: string }

export type NumberState = "available" | "in_use" | "quarantined";
export type NumberTab = "all" | NumberState;
export interface NumberRow { msisdn: string; state: NumberState; availableFromEpoch: number | null } // Unix seconds, set for quarantined numbers
export interface NumbersQuery { q: string; tab: NumberTab; page: number; pageSize: number }
export interface NumbersPage { items: NumberRow[]; total: number; counts: Record<NumberTab, number> }

export type BatchState = "requested" | "approved" | "sent_to_printer" | "in_stock" | "on_sale" | "locked";
export type VoucherState = BatchState | "used" | "expired";
export interface VoucherBatch {
  batchId: number;
  name: string;               // printed on every card, for example V-00007
  faceValueKobo: number;
  cardCount: number;
  cardsUsed: number;
  state: BatchState;
  requestedBy: string;
  requestedAt: number | null; // Unix seconds
  approvedBy: string | null;
  printedBy: string | null;
  printedAt: number | null;
}
export interface VoucherBatches { items: VoucherBatch[]; voucherValuesKobo: number[]; maxCards: number }
export interface VoucherCard {
  voucherId: number;
  last4: string;              // only the last four digits of the card number ever reach the screen
  batch: string;
  faceValueKobo: number;
  state: VoucherState;
  failedAttempts: number;     // failed redemptions in the last hour
  maxAttempts: number;        // 5 per card number per hour
  usedByMsisdn: string | null;
  usedAt: number | null;
}

export interface StockHistoryEntry { at: number; action: string; actor: string; detail: string }

// A batch moves forward one step at a time until it is on sale. Printing is its own step: it makes the cards and the
// PINs, once, as a PDF.
export type BatchAction = { kind: "advance"; to: "approved" | "in_stock" | "on_sale"; label: string } | { kind: "print"; label: string };
export const NEXT_BATCH_STEP: Partial<Record<BatchState, BatchAction>> = {
  requested: { kind: "advance", to: "approved", label: "Approve" },
  approved: { kind: "print", label: "Print PDF" },
  sent_to_printer: { kind: "advance", to: "in_stock", label: "Mark in stock" },
  in_stock: { kind: "advance", to: "on_sale", label: "Put on sale" },
};
