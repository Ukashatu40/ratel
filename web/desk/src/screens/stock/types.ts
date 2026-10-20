export interface SimSummary { inStock: number; inUse: number; retired: number }
export interface SimBatch { batchId: string; importedAt: number; total: number; inStock: number; inUse: number; importedBy: string }
// BSS keeps ICCID, IMSI and batch only. SIM secret keys (Ki/OPc) never come through this app.
export interface SimImportRow { iccid: string; imsi: string; batch: string }

export type NumberState = "available" | "in_use" | "quarantined";
export type NumberTab = "all" | NumberState;
export interface NumberRow { msisdn: string; state: NumberState; availableFromEpoch: number | null } // Unix seconds, set for quarantined numbers
export interface NumbersQuery { q: string; tab: NumberTab; page: number; pageSize: number }
export interface NumbersPage { items: NumberRow[]; total: number; counts: Record<NumberTab, number> }

export type BatchState = "requested" | "approved" | "sent_to_printer" | "in_stock" | "on_sale" | "expired";
export type VoucherState = BatchState | "used" | "locked";
export interface VoucherBatch { batchId: string; faceValueKobo: number; cardCount: number; state: BatchState; createdBy: string; createdAt: number }
export interface VoucherCard {
  voucherId: string;
  maskedNumber: string;       // only the last four digits of the card number ever reach the screen
  batchId: string;
  faceValueKobo: number;
  state: VoucherState;
  failedAttempts: number;     // failed redemptions in the last hour
  maxAttempts: number;        // 5 per card number per hour
  checkDigitValid: boolean;   // the Luhn check
  redeemedBy: string | null;
  redeemedAt: number | null;
}

export interface StockHistoryEntry { at: number; action: string; actor: string; detail: string }

// A batch moves forward one step at a time until it is on sale.
export const NEXT_BATCH_STEP: Partial<Record<BatchState, { label: string }>> = {
  requested: { label: "Approve" }, approved: { label: "Send to printer" }, sent_to_printer: { label: "Mark in stock" }, in_stock: { label: "Put on sale" },
};
