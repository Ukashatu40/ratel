// The ledger's entry kinds are not fixed by the PRD yet (TODO(PRD)). The API's `kind` is a free string; the code writes
// top_up (a payment or a voucher), purchase (a plan or bundle), vat and correction. Anything else is shown as it comes.
export type EntryKind = string;
export type LedgerTab = string; // "all" or an entry kind
export const KIND_LABEL: Record<string, string> = { top_up: "Top-ups", purchase: "Plan purchases", vat: "VAT", correction: "Corrections" };
export const KNOWN_KINDS = Object.keys(KIND_LABEL);

// One row of the append-only ledger. Money is whole kobo; credits are positive and debits negative.
export interface LedgerEntry {
  entryId: number;
  lineId: number;
  msisdn: string;
  amountKobo: number;
  kind: EntryKind;
  reference: string;
  createdAt: number;     // Unix seconds, UTC
}

// `line` is a line's id (the mock also takes an IMSI). null means every line.
export interface LedgerQuery { kind: LedgerTab; line: string | null; page: number; pageSize: number }
// counts are for the selected line (or all lines), ignoring the kind: "all" and one number per kind that has entries
export interface LedgerPage { items: LedgerEntry[]; total: number; counts: Record<string, number> }

export interface WalletSummary {
  totalBalanceKobo: number;
  walletsWithBalance: number;
  entriesToday: number;
  daily: { date: string; inKobo: number; outKobo: number }[]; // last 7 days, oldest first, date as YYYY-MM-DD (a Lagos day)
  // Last 7 daily values, oldest first. null when the API has none: RatelBSS keeps no daily balance history (TODO(PRD)).
  trends: { balance: number[]; wallets: number[]; entries: number[] } | null;
}

export interface LineWallet { lineId: number; msisdn: string; customerName: string | null; balanceKobo: number; ledgerSumKobo: number }
