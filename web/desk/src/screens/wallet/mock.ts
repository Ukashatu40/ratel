import { ApiError } from "../../lib/api";
import { mockFindLine } from "../lines/mock";
import type { LedgerEntry, LedgerPage, LedgerQuery, LineWallet, WalletSummary } from "./types";

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));
const nowSec = () => Math.floor(Date.now() / 1000);
const PRICE: Record<string, number> = { "Weekly 2GB": 120_000, "Starter 5GB": 350_000, "Family 20GB": 980_000 };

// Built once from the same lines the Lines screen shows. A wallet's balance is always the sum of its entries.
// The kinds are the API's: top_up (a payment or a voucher), purchase and vat (a plan's price, VAT inside it), correction.
const entries: LedgerEntry[] = [];
(() => {
  const now = nowSec();
  for (let n = 100; n < 237; n++) {
    const line = mockFindLine(n);
    if (!line || line.state === "awaiting_activation") continue;
    const price = PRICE[line.planName] ?? 350_000, net = Math.round((price * 1000) / 1075), vat = price - net;
    const top = 200_000 + ((n * 13_700) % 800_000), t0 = now - 86400 * (n % 13) - 3600 * (n % 7);
    const add = (kind: string, amountKobo: number, reference: string, at: number) =>
      entries.push({ entryId: 0, lineId: n, msisdn: line.msisdn, amountKobo, kind, reference, createdAt: Math.min(now, at) });
    add("top_up", top, n % 3 === 0 ? `VCH-B014-${String(n).padStart(4, "0")}` : `PAY-${77000 + n}`, t0);
    if (price <= top) { add("purchase", -net, `PLN-${line.planName.split(" ")[0].toUpperCase()}`, t0 + 30); add("vat", -vat, "", t0 + 31); }
    if (n % 23 === 0) add("correction", 20_000, "", t0 + 3600);
  }
  entries.sort((a, b) => b.createdAt - a.createdAt);
  entries.forEach((e, i) => { e.entryId = 904000 + entries.length - i; });
})();

const KINDS = ["top_up", "purchase", "vat", "correction"];
const dayKey = (t: number) => Math.floor((t + 3600) / 86400); // a Lagos day: WAT is UTC+1

export async function mockGetLedger({ kind, line, page, pageSize }: LedgerQuery): Promise<LedgerPage> {
  await wait(180);
  const found = line ? mockFindLine(line) : undefined;
  const rows = line ? entries.filter((e) => e.lineId === found?.lineId) : entries;
  const counts: Record<string, number> = { all: rows.length };
  KINDS.forEach((k) => { const n = rows.filter((e) => e.kind === k).length; if (n) counts[k] = n; });
  const shown = kind === "all" ? rows : rows.filter((e) => e.kind === kind);
  return { items: shown.slice((page - 1) * pageSize, page * pageSize), total: shown.length, counts };
}

export async function mockGetWallet(key: string): Promise<LineWallet> {
  await wait(150);
  const line = mockFindLine(key);
  if (!line) throw new ApiError(404, "line_not_found", "No such line");
  const sum = entries.filter((e) => e.lineId === line.lineId).reduce((s, e) => s + e.amountKobo, 0);
  return { lineId: line.lineId, msisdn: line.msisdn, customerName: line.customerName, balanceKobo: sum, ledgerSumKobo: sum };
}

export async function mockGetWalletSummary(): Promise<WalletSummary> {
  await wait(180);
  const today = dayKey(nowSec()), days = Array.from({ length: 7 }, (_, i) => today - 6 + i);
  const per = new Map<number, number>();
  entries.forEach((e) => per.set(e.lineId, (per.get(e.lineId) ?? 0) + e.amountKobo));
  const on = (d: number) => entries.filter((e) => dayKey(e.createdAt) === d);
  return {
    totalBalanceKobo: [...per.values()].reduce((s, v) => s + v, 0),
    walletsWithBalance: [...per.values()].filter((v) => v > 0).length,
    entriesToday: on(today).length,
    daily: days.map((d) => ({ date: new Date(d * 86400000).toISOString().slice(0, 10), inKobo: on(d).filter((e) => e.amountKobo > 0).reduce((s, e) => s + e.amountKobo, 0), outKobo: -on(d).filter((e) => e.amountKobo < 0).reduce((s, e) => s + e.amountKobo, 0) })),
    trends: null, // like the API: no daily balance history
  };
}
