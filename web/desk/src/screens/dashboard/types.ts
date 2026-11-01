// What the dashboard screen needs from RatelBSS (contracts/openapi.yaml, bss_dashboard). The mapping from the API's
// shape is in contract.ts.
export type LineState = "awaiting_activation" | "active" | "out_of_data" | "expired" | "suspended" | "terminated";

export interface AttentionItem {
  customerId: number;
  lineId: number | null;      // null for a customer who has no line yet
  customerName: string;
  msisdn: string | null;
  issue: "out_of_data" | "pending_kyc";
  sinceEpoch: number; // Unix seconds, UTC
}

export interface DashboardData {
  counts: Record<LineState, number>;        // lines by state
  kycPending: number;
  topupsTodayKobo: number;                  // whole kobo, never decimals
  topupsYesterdayKobo: number;
  topupsLast7Days: { date: string; amountKobo: number }[]; // oldest first, date as YYYY-MM-DD
  // Last 7 daily values, oldest first. null when the API has none: RatelBSS keeps no daily snapshots of line counts
  // (TODO(PRD)), so the real dashboard shows no trend lines.
  trends: { active: number[]; outOfData: number[]; kycPending: number[] } | null;
  attention: AttentionItem[];
}
