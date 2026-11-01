import type { LedgerEntry, LedgerPage, LineWallet, WalletSummary } from "./types";

// The wire shapes of the wallet and ledger screens (contracts/openapi.yaml) and their mappers.
// tests/fixtures/contract/LedgerPage.json, WalletSummary.json and LineWallet.json are checked against the contract.
export interface WireLedgerEntry { entry_id: number; line_id: number; msisdn: string; amount_kobo: number; kind: string; reference: string; created_at: number }
export interface WireLedgerPage { entries: WireLedgerEntry[]; total: number; counts: Record<string, number> }
export interface WireWalletSummary {
  total_balance_kobo: number; wallets_with_balance: number; entries_today: number;
  daily: { date: string; in_kobo: number; out_kobo: number }[];
}
export interface WireLineWalletBody { line_id: number; balance_kobo: number; ledger_sum_kobo: number }

export const ledgerEntryFromWire = (e: WireLedgerEntry): LedgerEntry => ({
  entryId: e.entry_id, lineId: e.line_id, msisdn: e.msisdn, amountKobo: e.amount_kobo, kind: e.kind, reference: e.reference, createdAt: e.created_at,
});
export const ledgerPageFromWire = (p: WireLedgerPage): LedgerPage => ({ items: p.entries.map(ledgerEntryFromWire), total: p.total, counts: p.counts });

export const walletSummaryFromWire = (s: WireWalletSummary): WalletSummary => ({
  totalBalanceKobo: s.total_balance_kobo, walletsWithBalance: s.wallets_with_balance, entriesToday: s.entries_today,
  daily: s.daily.map((d) => ({ date: d.date, inKobo: d.in_kobo, outKobo: d.out_kobo })), trends: null,
});

// The wallet answers only its numbers; the number and the name come from the line and its customer.
export const lineWalletFromWire = (w: WireLineWalletBody, msisdn: string, customerName: string | null): LineWallet => ({
  lineId: w.line_id, msisdn, customerName, balanceKobo: w.balance_kobo, ledgerSumKobo: w.ledger_sum_kobo,
});
