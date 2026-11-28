import { apiGet, apiPost, apiPostFile } from "../../lib/api";
import { batchesFromWire, cardFromWire, type WireBatch, type WireBatches, type WireCard } from "./contract";
import {
  mockAdvanceBatch, mockGetNumbers, mockGetSimBatches, mockGetSimSummary, mockGetStockHistory, mockGetVoucherBatches,
  mockImportSims, mockLockBatch, mockLockCard, mockLookupCard, mockPrintBatch, mockRequestBatch,
} from "./mock";
import type { NumbersPage, NumbersQuery, SimBatch, SimImportRow, SimSummary, StockHistoryEntry, VoucherBatches, VoucherCard } from "./types";

// ASSUMED endpoints (confirm with the RatelBSS developers; only this file should change):
//   GET  /v1/stock/sims/summary            -> { inStock, inUse, retired }
//   GET  /v1/stock/sims/batches            -> SimBatch[]
//   POST /v1/stock/sims/import { sims }    -> { imported }      (ICCID, IMSI and batch only: keys go to RatelLink directly)
//   GET  /v1/stock/numbers?q=&state=&page=&pageSize=  -> { items, total, counts }
// The voucher operations are in the contract (desk_*_voucher*): batches, the one-time printed sheet, lookup and locks.
//   GET  /v1/stock/history                 -> StockHistoryEntry[]
// The full card number is sent in a request body (never in a URL) and only the last four digits come back.
const isMock = () => import.meta.env.VITE_USE_MOCK === "true";

export const getSimSummary = (): Promise<SimSummary> => (isMock() ? mockGetSimSummary() : apiGet<SimSummary>("/v1/stock/sims/summary"));
export const getSimBatches = (): Promise<SimBatch[]> => (isMock() ? mockGetSimBatches() : apiGet<SimBatch[]>("/v1/stock/sims/batches"));
export const importSims = (sims: SimImportRow[], key: string): Promise<{ imported: number }> => (isMock() ? mockImportSims(sims) : apiPost<{ imported: number }>("/v1/stock/sims/import", { sims }, key));

export const getNumbers = (q: NumbersQuery): Promise<NumbersPage> =>
  isMock() ? mockGetNumbers(q) : apiGet<NumbersPage>(`/v1/stock/numbers?${new URLSearchParams({ q: q.q, state: q.tab, page: String(q.page), pageSize: String(q.pageSize) })}`);

export const getVoucherBatches = async (): Promise<VoucherBatches> =>
  isMock() ? mockGetVoucherBatches() : batchesFromWire(await apiGet<WireBatches>("/v1/voucher-batches"));
export const requestBatch = async (input: { faceValueKobo: number; cardCount: number; reason: string }, key: string): Promise<void> => {
  if (isMock()) return mockRequestBatch(input);
  await apiPost<{ batch: WireBatch }>("/v1/voucher-batches", { face_value_kobo: input.faceValueKobo, card_count: input.cardCount, reason: input.reason }, key);
};
export const advanceBatch = async (batchId: number, to: "approved" | "in_stock" | "on_sale", reason: string, key: string): Promise<void> => {
  if (isMock()) return mockAdvanceBatch(batchId, to);
  await apiPost<WireBatch>(`/v1/voucher-batches/${batchId}/advance`, { state: to, reason }, key);
};
// The sheet holds live PINs and can be fetched once only: it goes straight to the browser's download, nowhere else.
export const printBatch = (batchId: number, key: string): Promise<Blob> =>
  isMock() ? mockPrintBatch(batchId) : apiPostFile(`/v1/voucher-batches/${batchId}/print`, key);
export const lockBatch = async (batchId: number, reason: string, key: string): Promise<void> => {
  if (isMock()) return mockLockBatch(batchId, reason);
  await apiPost<WireBatch>(`/v1/voucher-batches/${batchId}/lock`, { reason }, key);
};
export const lookupCard = async (cardNumber: string): Promise<VoucherCard> =>
  isMock() ? mockLookupCard(cardNumber) : cardFromWire(await apiPost<WireCard>("/v1/vouchers/lookup", { card_number: cardNumber }));
export const lockCard = async (voucherId: number, reason: string, key: string): Promise<void> => {
  if (isMock()) return mockLockCard(voucherId, reason);
  await apiPost<WireCard>(`/v1/vouchers/${voucherId}/lock`, { reason }, key);
};

export const getStockHistory = (): Promise<StockHistoryEntry[]> => (isMock() ? mockGetStockHistory() : apiGet<StockHistoryEntry[]>("/v1/stock/history"));
