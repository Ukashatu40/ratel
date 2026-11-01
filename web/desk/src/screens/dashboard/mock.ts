import type { DashboardData } from "./types";

// WAT is UTC+1, so subtract an hour to get the UTC epoch for a WAT wall-clock time.
const wat = (y: number, mo: number, d: number, h: number, mi: number) => Date.UTC(y, mo - 1, d, h - 1, mi) / 1000;
const k = (naira: number) => naira * 100; // naira to kobo

export const mockDashboard: DashboardData = {
  counts: { active: 1248, out_of_data: 86, awaiting_activation: 14, suspended: 9, expired: 33, terminated: 5 },
  kycPending: 14,
  topupsTodayKobo: k(412_500),
  topupsYesterdayKobo: k(380_500),
  topupsLast7Days: [
    ["2026-10-02", 310_000], ["2026-10-03", 360_000], ["2026-10-04", 290_000], ["2026-10-05", 420_000],
    ["2026-10-06", 380_000], ["2026-10-07", 380_500], ["2026-10-08", 412_500],
  ].map(([date, n]) => ({ date: date as string, amountKobo: k(n as number) })),
  trends: null, // like the API: no daily snapshots of line counts
  attention: [
    { customerId: 12, lineId: 112, customerName: "Musa Ibrahim", msisdn: "2347000000112", issue: "out_of_data", sinceEpoch: wat(2026, 10, 8, 7, 15) },
    { customerId: 27, lineId: 127, customerName: "Fatima Bello", msisdn: "2347000000127", issue: "out_of_data", sinceEpoch: wat(2026, 10, 8, 6, 50) },
    { customerId: 1, lineId: null, customerName: "Aisha Sani", msisdn: null, issue: "pending_kyc", sinceEpoch: wat(2026, 10, 7, 16, 20) },
    { customerId: 31, lineId: 131, customerName: "Sani Danjuma", msisdn: "2347000000131", issue: "out_of_data", sinceEpoch: wat(2026, 10, 7, 22, 40) },
    { customerId: 63, lineId: 163, customerName: "Hauwa Garba", msisdn: "2347000000163", issue: "pending_kyc", sinceEpoch: wat(2026, 10, 7, 14, 5) },
  ],
};
