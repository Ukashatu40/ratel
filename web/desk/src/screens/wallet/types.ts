export type EntryKind = "top_up" | "plan_purchase" | "vat" | "voucher_redemption" | "correction";
export type LedgerTab = "all" | EntryKind;

// One row of the append-only ledger. Money is whole kobo; credits are positive and debits negative.
export interface LedgerEntry {
  entryId: string;
  lineId: string;
  imsi: string;          // lets the screen link to the line (assumed: the ledger itself keys on line_id)
  msisdn: string;
  amountKobo: number;
  kind: EntryKind;
  reference: string;
  createdAt: number;     // Unix seconds, UTC
}

export interface LedgerQuery { kind: LedgerTab; line: string | null; page: number; pageSize: number }
// counts are for the selected line (or all lines), one number per kind
export interface LedgerPage { items: LedgerEntry[]; total: number; counts: Record<LedgerTab, number> }

export interface WalletSummary {
  totalBalanceKobo: number; balanceTrendKobo: number[];   // last 7 days, oldest first
  walletsWithBalance: number; walletsTrend: number[];
  entriesToday: number; entriesTrend: number[];
  daily: { date: string; inKobo: number; outKobo: number }[]; // last 7 days, date as YYYY-MM-DD (WAT)
}

export interface LineWallet { imsi: string; msisdn: string; customerName: string; balanceKobo: number; ledgerSumKobo: number }
