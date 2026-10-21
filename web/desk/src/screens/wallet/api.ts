import { apiGet } from "../../lib/api";
import { mockGetLedger, mockGetWallet, mockGetWalletSummary } from "./mock";
import type { LedgerPage, LedgerQuery, LineWallet, WalletSummary } from "./types";

// ASSUMED endpoints (confirm with the RatelBSS developers; only this file should change):
//   GET /v1/wallet/summary                                  -> WalletSummary
//   GET /v1/ledger?kind=&line=&page=&pageSize=               -> { items, total, counts }   (line = IMSI)
//   GET /v1/wallets/{imsi}                                  -> { balanceKobo, ledgerSumKobo, ... }
// The ledger is read-only here: entries are only ever appended by the system, and a correction is a new entry.
const isMock = () => import.meta.env.VITE_USE_MOCK === "true";

export const getWalletSummary = (): Promise<WalletSummary> => (isMock() ? mockGetWalletSummary() : apiGet<WalletSummary>("/v1/wallet/summary"));
export const getLedger = (q: LedgerQuery): Promise<LedgerPage> =>
  isMock() ? mockGetLedger(q) : apiGet<LedgerPage>(`/v1/ledger?${new URLSearchParams({ kind: q.kind, line: q.line ?? "", page: String(q.page), pageSize: String(q.pageSize) })}`);
export const getLineWallet = (imsi: string): Promise<LineWallet> => (isMock() ? mockGetWallet(imsi) : apiGet<LineWallet>(`/v1/wallets/${imsi}`));
