export interface SalesDay { date: string; revenueKobo: number; vatKobo: number }   // revenue includes VAT; date as YYYY-MM-DD (WAT)
export interface ReportsOverview {
  days: number;
  salesPerDay: SalesDay[];                                       // oldest first, one per day
  revenueByPlan: { name: string; revenueKobo: number }[];        // before VAT
  dataUsagePerDay: { date: string; bytes: number }[];            // rated data usage
  voucherRedemptionsPerDay: { date: string; count: number; valueKobo: number }[];
}

export interface Mismatch { lineId: string; imsi: string; msisdn: string; walletKobo: number; ledgerSumKobo: number }
export interface Reconciliation {
  status: "ok" | "mismatch" | "failed" | "running";
  ranAt: number;                                                  // Unix seconds, UTC
  walletsChecked: number;
  matching: number;
  mismatches: Mismatch[];
  recentRuns: { date: string; checked: number; mismatchCount: number }[]; // last 7 nights, oldest first
}
