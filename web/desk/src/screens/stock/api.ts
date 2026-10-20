import { apiGet, apiPost } from "../../lib/api";
import {
  mockAdvanceBatch, mockGetNumbers, mockGetSimBatches, mockGetSimSummary, mockGetStockHistory, mockGetVoucherBatches,
  mockImportSims, mockLockCard, mockLookupCard, mockRequestBatch,
} from "./mock";
import type { NumbersPage, NumbersQuery, SimBatch, SimImportRow, SimSummary, StockHistoryEntry, VoucherBatch, VoucherCard } from "./types";

// ASSUMED endpoints (confirm with the RatelBSS developers; only this file should change):
//   GET  /v1/stock/sims/summary            -> { inStock, inUse, retired }
//   GET  /v1/stock/sims/batches            -> SimBatch[]
//   POST /v1/stock/sims/import { sims }    -> { imported }      (ICCID, IMSI and batch only: keys go to RatelLink directly)
//   GET  /v1/stock/numbers?q=&state=&page=&pageSize=  -> { items, total, counts }
//   GET  /v1/voucher-batches, POST /v1/voucher-batches { faceValueKobo, cardCount }, POST /v1/voucher-batches/{id}/advance
//   POST /v1/vouchers/lookup { cardNumber } -> VoucherCard (masked), POST /v1/vouchers/{voucherId}/lock { reason }
//   GET  /v1/stock/history                 -> StockHistoryEntry[]
// The full card number is sent in a request body (never in a URL) and only the last four digits come back.
const isMock = () => import.meta.env.VITE_USE_MOCK === "true";

export const getSimSummary = (): Promise<SimSummary> => (isMock() ? mockGetSimSummary() : apiGet<SimSummary>("/v1/stock/sims/summary"));
export const getSimBatches = (): Promise<SimBatch[]> => (isMock() ? mockGetSimBatches() : apiGet<SimBatch[]>("/v1/stock/sims/batches"));
export const importSims = (sims: SimImportRow[], key: string): Promise<{ imported: number }> => (isMock() ? mockImportSims(sims) : apiPost<{ imported: number }>("/v1/stock/sims/import", { sims }, key));

export const getNumbers = (q: NumbersQuery): Promise<NumbersPage> =>
  isMock() ? mockGetNumbers(q) : apiGet<NumbersPage>(`/v1/stock/numbers?${new URLSearchParams({ q: q.q, state: q.tab, page: String(q.page), pageSize: String(q.pageSize) })}`);

export const getVoucherBatches = (): Promise<VoucherBatch[]> => (isMock() ? mockGetVoucherBatches() : apiGet<VoucherBatch[]>("/v1/voucher-batches"));
export const requestBatch = (input: { faceValueKobo: number; cardCount: number }, key: string): Promise<void> => (isMock() ? mockRequestBatch(input) : apiPost<void>("/v1/voucher-batches", input, key));
export const advanceBatch = (batchId: string, key: string): Promise<void> => (isMock() ? mockAdvanceBatch(batchId) : apiPost<void>(`/v1/voucher-batches/${batchId}/advance`, {}, key));
export const lookupCard = (cardNumber: string): Promise<VoucherCard> => (isMock() ? mockLookupCard(cardNumber) : apiPost<VoucherCard>("/v1/vouchers/lookup", { cardNumber }));
export const lockCard = (voucherId: string, reason: string, key: string): Promise<void> => (isMock() ? mockLockCard(voucherId, reason) : apiPost<void>(`/v1/vouchers/${voucherId}/lock`, { reason }, key));

export const getStockHistory = (): Promise<StockHistoryEntry[]> => (isMock() ? mockGetStockHistory() : apiGet<StockHistoryEntry[]>("/v1/stock/history"));
