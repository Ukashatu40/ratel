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
  trends: {
    active: [1190, 1204, 1210, 1222, 1230, 1241, 1248],
    outOfData: [60, 64, 70, 66, 74, 80, 86],
    kycPending: [22, 20, 19, 18, 17, 15, 14],
  },
  attention: [
    { imsi: "621000000000112", customerName: "Musa Ibrahim", msisdn: "+234 700 000 0112", issue: "out_of_data", planName: "Starter 5GB", sinceEpoch: wat(2026, 10, 8, 7, 15) },
    { imsi: "621000000000127", customerName: "Fatima Bello", msisdn: "+234 700 000 0127", issue: "out_of_data", planName: "Weekly 2GB", sinceEpoch: wat(2026, 10, 8, 6, 50) },
    { imsi: "621000000000150", customerName: "Aisha Sani", msisdn: "+234 700 000 0150", issue: "pending_kyc", planName: "Starter 5GB", sinceEpoch: wat(2026, 10, 7, 16, 20) },
    { imsi: "621000000000131", customerName: "Sani Danjuma", msisdn: "+234 700 000 0131", issue: "out_of_data", planName: "Starter 5GB", sinceEpoch: wat(2026, 10, 7, 22, 40) },
    { imsi: "621000000000163", customerName: "Hauwa Garba", msisdn: "+234 700 000 0163", issue: "pending_kyc", planName: "Family 20GB", sinceEpoch: wat(2026, 10, 7, 14, 5) },
  ],
};