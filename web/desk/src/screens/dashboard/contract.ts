import type { AttentionItem, DashboardData, LineState } from "./types";

// The wire shape of bss_dashboard (contracts/openapi.yaml) and its mapper.
// tests/fixtures/contract/Dashboard.json is checked against the contract and against this mapper.
export interface WireAttentionItem {
  issue: "out_of_data" | "pending_kyc"; customer_id: number; line_id: number | null; customer_name: string; msisdn: string | null; since: number;
}
export interface WireDashboard {
  line_counts: Record<"all" | LineState, number>;
  kyc_pending: number;
  topups_today_kobo: number;
  topups_yesterday_kobo: number;
  topups_last_7_days: { date: string; amount_kobo: number }[];
  attention: WireAttentionItem[];
}

export const attentionFromWire = (a: WireAttentionItem): AttentionItem => ({
  customerId: a.customer_id, lineId: a.line_id, customerName: a.customer_name, msisdn: a.msisdn, issue: a.issue, sinceEpoch: a.since,
});

export const dashboardFromWire = (d: WireDashboard): DashboardData => ({
  counts: {
    awaiting_activation: d.line_counts.awaiting_activation, active: d.line_counts.active, out_of_data: d.line_counts.out_of_data,
    expired: d.line_counts.expired, suspended: d.line_counts.suspended, terminated: d.line_counts.terminated,
  },
  kycPending: d.kyc_pending,
  topupsTodayKobo: d.topups_today_kobo,
  topupsYesterdayKobo: d.topups_yesterday_kobo,
  topupsLast7Days: d.topups_last_7_days.map((p) => ({ date: p.date, amountKobo: p.amount_kobo })),
  trends: null,
  attention: d.attention.map(attentionFromWire),
});
