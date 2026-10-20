import { ApiError } from "../../lib/api";
import { mockFindLine } from "../lines/mock";
import { vatKobo } from "../sell-sim/pricing";
import type { EntryKind, LedgerEntry, LedgerPage, LedgerQuery, LedgerTab, LineWallet, WalletSummary } from "./types";

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));
const nowSec = () => Math.floor(Date.now() / 1000);
const PRICE: Record<string, number> = { "Weekly 2GB": 120_000, "Starter 5GB": 350_000, "Family 20GB": 980_000 };

// Built once from the same lines the Lines screen shows. A wallet's balance is always the sum of its entries.
const entries: LedgerEntry[] = [];
(() => {
  const now = nowSec();
  for (let n = 100; n < 237; n++) {
    const imsi = `621000000000${n}`, line = mockFindLine(imsi);
    if (!line || line.state === "awaiting_activation") continue;
    const lineId = `L-${String(n).padStart(4, "0")}`, price = PRICE[line.planName] ?? 350_000, vat = vatKobo(price);
    const top = 200_000 + ((n * 13_700) % 800_000), t0 = now - 86400 * (n % 13) - 3600 * (n % 7);
    const add = (kind: EntryKind, amountKobo: number, reference: string, at: number) =>
      entries.push({ entryId: "", lineId, imsi, msisdn: line.msisdn, amountKobo, kind, reference, createdAt: Math.min(now, at) });
    add(n % 3 === 0 ? "voucher_redemption" : "top_up", top, n % 3 === 0 ? `VCH-B014-${String(n).padStart(4, "0")}` : `PAY-${77000 + n}`, t0);
    if (price + vat <= top) { add("plan_purchase", -price, `PLN-${line.planName.split(" ")[0].toUpperCase()}`, t0 + 30); add("vat", -vat, "", t0 + 31); }
    if (n % 23 === 0) add("correction", 20_000, "", t0 + 3600);
  }
  entries.sort((a, b) => b.createdAt - a.createdAt);
  entries.forEach((e, i) => { e.entryId = `E-${904000 + entries.length - i}`; });
  // VAT and correction entries point at the entry they belong to
  const purchase = new Map(entries.filter((e) => e.kind === "plan_purchase").map((e) => [e.imsi, e.entryId]));
  const first = new Map(entries.filter((e) => e.kind === "top_up" || e.kind === "voucher_redemption").map((e) => [e.imsi, e.entryId]));
  entries.forEach((e) => { if (e.kind === "vat") e.reference = purchase.get(e.imsi) ?? ""; if (e.kind === "correction") e.reference = first.get(e.imsi) ?? ""; });
})();

const KINDS: EntryKind[] = ["top_up", "plan_purchase", "vat", "voucher_redemption", "correction"];
const dayKey = (t: number) => Math.floor((t + 3600) / 86400); // WAT is UTC+1

export async function mockGetLedger({ kind, line, page, pageSize }: LedgerQuery): Promise<LedgerPage> {
  await wait(180);
  const rows = line ? entries.filter((e) => e.imsi === line) : entries;
  const counts = { all: rows.length, ...Object.fromEntries(KINDS.map((k) => [k, rows.filter((e) => e.kind === k).length])) } as Record<LedgerTab, number>;
  const shown = kind === "all" ? rows : rows.filter((e) => e.kind === kind);
  return { items: shown.slice((page - 1) * pageSize, page * pageSize), total: shown.length, counts };
}

export async function mockGetWallet(imsi: string): Promise<LineWallet> {
  await wait(150);
  const line = mockFindLine(imsi);
  if (!line) throw new ApiError(404, "line_not_found", "No such line");
  const sum = entries.filter((e) => e.imsi === imsi).reduce((s, e) => s + e.amountKobo, 0);
  return { imsi, msisdn: line.msisdn, customerName: line.customerName, balanceKobo: sum, ledgerSumKobo: sum };
}

export async function mockGetWalletSummary(): Promise<WalletSummary> {
  await wait(180);
  const today = dayKey(nowSec()), days = Array.from({ length: 7 }, (_, i) => today - 6 + i);
  const balancesUpTo = (d: number) => {
    const per = new Map<string, number>();
    entries.forEach((e) => { if (dayKey(e.createdAt) <= d) per.set(e.imsi, (per.get(e.imsi) ?? 0) + e.amountKobo); });
    return [...per.values()];
  };
  const bal = days.map(balancesUpTo);
  const on = (d: number) => entries.filter((e) => dayKey(e.createdAt) === d);
  return {
    totalBalanceKobo: bal[6].reduce((s, v) => s + v, 0), balanceTrendKobo: bal.map((b) => b.reduce((s, v) => s + v, 0)),
    walletsWithBalance: bal[6].filter((v) => v > 0).length, walletsTrend: bal.map((b) => b.filter((v) => v > 0).length),
    entriesToday: on(today).length, entriesTrend: days.map((d) => on(d).length),
    daily: days.map((d) => ({ date: new Date(d * 86400000).toISOString().slice(0, 10), inKobo: on(d).filter((e) => e.amountKobo > 0).reduce((s, e) => s + e.amountKobo, 0), outKobo: -on(d).filter((e) => e.amountKobo < 0).reduce((s, e) => s + e.amountKobo, 0) })),
  };
}
