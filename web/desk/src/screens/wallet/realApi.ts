import { apiGet } from "../../lib/api";
import { wireId, type WireCustomer, type WireLine } from "../sell-sim/contract";
import { ledgerPageFromWire, lineWalletFromWire, walletSummaryFromWire, type WireLedgerPage, type WireLineWalletBody, type WireWalletSummary } from "./contract";
import type { LedgerPage, LedgerQuery, LineWallet, WalletSummary } from "./types";

// The real calls of the wallet and ledger screens, to the paths and shapes of contracts/openapi.yaml.
// The ledger is read-only: entries are only ever appended by the system, and a correction is a new entry.
export const getWalletSummary = (): Promise<WalletSummary> => apiGet<WireWalletSummary>("/v1/wallet/summary").then(walletSummaryFromWire);

export const getLedger = async (q: LedgerQuery): Promise<LedgerPage> => {
  const params = new URLSearchParams({ page: String(q.page), page_size: String(q.pageSize) });
  if (q.kind !== "all") params.set("kind", q.kind);
  if (q.line) params.set("line_id", String(wireId(q.line)));
  return ledgerPageFromWire(await apiGet<WireLedgerPage>(`/v1/ledger?${params}`));
};

export const getLineWallet = async (key: string): Promise<LineWallet> => {
  const id = wireId(key);
  const line = await apiGet<WireLine>(`/v1/lines/${id}`);
  const [wallet, customer] = await Promise.all([
    apiGet<WireLineWalletBody>(`/v1/lines/${id}/wallet`),
    apiGet<WireCustomer>(`/v1/customers/${line.customer_id}`),
  ]);
  return lineWalletFromWire(wallet, line.msisdn, customer.name); // only the name of the customer is kept
};
