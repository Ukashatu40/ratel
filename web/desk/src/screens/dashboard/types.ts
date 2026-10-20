// What the dashboard screen needs from RatelBSS. If the real API differs, adapt it in api.ts, not in the components.
export type LineState = "awaiting_activation" | "active" | "out_of_data" | "expired" | "suspended" | "terminated";

export interface AttentionItem {
  imsi: string;
  customerName: string;
  msisdn: string;
  issue: "out_of_data" | "pending_kyc";
  planName: string;
  sinceEpoch: number; // Unix seconds, UTC
}

export interface DashboardData {
  counts: Record<LineState, number>;        // lines by state
  kycPending: number;
  topupsTodayKobo: number;                  // whole kobo, never decimals
  topupsYesterdayKobo: number;
  topupsLast7Days: { date: string; amountKobo: number }[]; // oldest first, date as YYYY-MM-DD
  trends: { active: number[]; outOfData: number[]; kycPending: number[] }; // last 7 daily values, oldest first
  attention: AttentionItem[];
}