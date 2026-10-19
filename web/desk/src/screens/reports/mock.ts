import type { Mismatch, Reconciliation, ReportsOverview } from "./types";

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));
const nowSec = () => Math.floor(Date.now() / 1000);
const dayKey = (t: number) => Math.floor((t + 3600) / 86400); // WAT is UTC+1
const iso = (d: number) => new Date(d * 86400000).toISOString().slice(0, 10);
// small deterministic "random" so the same day always shows the same figure
const jitter = (d: number, salt: number) => (((d * 9301 + salt * 49297) % 233280) / 233280);

export async function mockGetOverview(days: number): Promise<ReportsOverview> {
  await wait(250);
  const today = dayKey(nowSec()), keys = Array.from({ length: days }, (_, i) => today - days + 1 + i);
  const salesPerDay = keys.map((d) => {
    const naira = 760_000 + Math.round(jitter(d, 1) * 560_000), revenueKobo = naira * 100;
    return { date: iso(d), revenueKobo, vatKobo: Math.round((revenueKobo * 75) / 1075) }; // VAT (7.5%) is part of what was charged
  });
  const net = salesPerDay.reduce((s, x) => s + x.revenueKobo - x.vatKobo, 0);
  const shares: [string, number][] = [["Starter 5GB", 46], ["Family 20GB", 31], ["Weekly 2GB", 14], ["Bundles", 9]];
  return {
    days, salesPerDay,
    revenueByPlan: shares.map(([name, p]) => ({ name, revenueKobo: Math.round((net * p) / 100) })),
    dataUsagePerDay: keys.map((d) => ({ date: iso(d), bytes: Math.round(3.0e12 + jitter(d, 2) * 1.2e12) })),
    voucherRedemptionsPerDay: keys.map((d) => { const count = 240 + Math.round(jitter(d, 3) * 160); return { date: iso(d), count, valueKobo: count * 100_000 }; }),
  };
}

// Set VITE_MOCK_RECON=mismatch in .env.local to see how a failed night looks.
const DEMO_MISMATCH = import.meta.env.VITE_MOCK_RECON === "mismatch";

export async function mockGetReconciliation(): Promise<Reconciliation> {
  await wait(200);
  const today = dayKey(nowSec()), checked = 1248;
  const mismatches: Mismatch[] = DEMO_MISMATCH
    ? [
        { lineId: "L-0112", imsi: "621000000000112", msisdn: "+234 700 000 0112", walletKobo: 350_000, ledgerSumKobo: 323_750 },
        { lineId: "L-0140", imsi: "621000000000140", msisdn: "+234 700 000 0140", walletKobo: 120_000, ledgerSumKobo: 130_000 },
      ]
    : [];
  return {
    status: mismatches.length ? "mismatch" : "ok",
    ranAt: today * 86400 - 3600 + 1800, // 00:30 WAT today
    walletsChecked: checked, matching: checked - mismatches.length, mismatches,
    recentRuns: Array.from({ length: 7 }, (_, i) => ({ date: iso(today - 6 + i), checked, mismatchCount: DEMO_MISMATCH && i === 6 ? mismatches.length : 0 })),
  };
}
