import { ApiError } from "../../lib/api";
import { NEXT_BATCH_STEP } from "./types";
import type { BatchState, NumberRow, NumbersPage, NumbersQuery, SimBatch, SimImportRow, SimSummary, StockHistoryEntry, VoucherBatch, VoucherBatches, VoucherCard, VoucherState } from "./types";

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));
const nowSec = () => Math.floor(Date.now() / 1000);
const ACTOR = "Amina Yusuf";

// DEMO ONLY: quarantine window for the demo. The real period is set by compliance (PRD decision 4);
// this file must not be treated as a source of truth for it.
const DEMO_QUARANTINE_DAYS = 10;

// ---- history (every stock change is recorded)
const history: StockHistoryEntry[] = [
  { at: nowSec() - 2 * 86400, action: "SIM batch imported", actor: "Ibrahim Danladi", detail: "SIM-2026-007, 2,000 SIMs" },
  { at: nowSec() - 3 * 3600, action: "Voucher batch approved", actor: "Ibrahim Danladi", detail: "V-00004" },
];
const log = (action: string, detail: string) => history.push({ at: nowSec(), action, actor: ACTOR, detail });
export async function mockGetStockHistory(): Promise<StockHistoryEntry[]> { await wait(150); return [...history].sort((a, b) => b.at - a.at).slice(0, 50); }

// ---- SIMs
const summary: SimSummary = { inStock: 2400, inUse: 1150, retired: 42 };
const simBatches: SimBatch[] = [
  { batchId: "SIM-2026-007", importedAt: nowSec() - 2 * 86400, total: 2000, inStock: 1640, inUse: 360, importedBy: "Ibrahim Danladi" },
  { batchId: "SIM-2026-006", importedAt: nowSec() - 16 * 86400, total: 1500, inStock: 760, inUse: 740, importedBy: "Ibrahim Danladi" },
  { batchId: "SIM-2026-005", importedAt: nowSec() - 35 * 86400, total: 1000, inStock: 0, inUse: 958, importedBy: "Bashir Aliyu" },
];
export async function mockGetSimSummary(): Promise<SimSummary> { await wait(150); return { ...summary }; }
export async function mockGetSimBatches(): Promise<SimBatch[]> { await wait(150); return simBatches.map((b) => ({ ...b })); }
export async function mockImportSims(rows: SimImportRow[]): Promise<{ imported: number }> {
  await wait(700);
  const byBatch = new Map<string, number>();
  rows.forEach((r) => byBatch.set(r.batch, (byBatch.get(r.batch) ?? 0) + 1));
  byBatch.forEach((n, batchId) => {
    simBatches.unshift({ batchId, importedAt: nowSec(), total: n, inStock: n, inUse: 0, importedBy: ACTOR });
    log("SIM batch imported", `${batchId}, ${n} SIMs`);
  });
  summary.inStock += rows.length;
  return { imported: rows.length };
}

// ---- Numbers
const numbers: NumberRow[] = Array.from({ length: 60 }, (_, i) => {
  const n = 100 + i, msisdn = `+234 700 000 ${String(n).padStart(4, "0")}`;
  if (n >= 150 && n <= 154) return { msisdn, state: "available" as const, availableFromEpoch: null };
  if (i % 9 === 0) return { msisdn, state: "quarantined" as const, availableFromEpoch: nowSec() + (((i % DEMO_QUARANTINE_DAYS) + 1) * 86400) };
  return { msisdn, state: i % 4 === 0 ? ("available" as const) : ("in_use" as const), availableFromEpoch: null };
});
export async function mockGetNumbers({ q, tab, page, pageSize }: NumbersQuery): Promise<NumbersPage> {
  await wait(150);
  const digits = q.replace(/\s/g, "");
  const found = digits ? numbers.filter((n) => n.msisdn.replace(/\s/g, "").includes(digits)) : numbers;
  const count = (t: NumbersQuery["tab"]) => (t === "all" ? found.length : found.filter((n) => n.state === t).length);
  const shown = tab === "all" ? found : found.filter((n) => n.state === tab);
  return { items: shown.slice((page - 1) * pageSize, page * pageSize), total: shown.length, counts: { all: count("all"), available: count("available"), in_use: count("in_use"), quarantined: count("quarantined") } };
}

// ---- Vouchers
const VALUES = [10_000, 20_000, 50_000, 100_000, 200_000];
const batch = (batchId: number, faceValueKobo: number, cardCount: number, state: BatchState, ago: number, cardsUsed = 0): VoucherBatch => ({
  batchId, name: `V-${String(batchId).padStart(5, "0")}`, faceValueKobo, cardCount, cardsUsed, state, requestedBy: ACTOR, requestedAt: nowSec() - ago,
  approvedBy: state === "requested" ? null : ACTOR, printedBy: ["requested", "approved"].includes(state) ? null : ACTOR, printedAt: ["requested", "approved"].includes(state) ? null : nowSec() - ago + 3600,
});
const batches: VoucherBatch[] = [batch(4, 50_000, 120, "approved", 86400), batch(3, 100_000, 240, "in_stock", 6 * 86400), batch(2, 20_000, 240, "on_sale", 20 * 86400, 37)];
interface Card { voucherId: number; number: string; batch: string; faceValueKobo: number; state: VoucherState; failedAttempts: number; usedByMsisdn: string | null; usedAt: number | null }
// Sample cards to try in the lookup (card numbers have 20 digits).
const cards: Card[] = [
  { voucherId: 1, number: "10000000000000004821", batch: "V-00003", faceValueKobo: 100_000, state: "locked", failedAttempts: 5, usedByMsisdn: null, usedAt: null },
  { voucherId: 2, number: "10000000000000001111", batch: "V-00003", faceValueKobo: 100_000, state: "in_stock", failedAttempts: 0, usedByMsisdn: null, usedAt: null },
  { voucherId: 3, number: "10000000000000002222", batch: "V-00002", faceValueKobo: 20_000, state: "on_sale", failedAttempts: 3, usedByMsisdn: null, usedAt: null },
  { voucherId: 4, number: "10000000000000003333", batch: "V-00002", faceValueKobo: 20_000, state: "used", failedAttempts: 0, usedByMsisdn: "2347000000101", usedAt: nowSec() - 3 * 86400 },
];
const toCard = (c: Card): VoucherCard => ({ voucherId: c.voucherId, last4: c.number.slice(-4), batch: c.batch, faceValueKobo: c.faceValueKobo, state: c.state, failedAttempts: c.failedAttempts, maxAttempts: 5, usedByMsisdn: c.usedByMsisdn, usedAt: c.usedAt });
const find = (batchId: number): number => {
  const i = batches.findIndex((b) => b.batchId === batchId);
  if (i < 0) throw new ApiError(404, "not_found", "No such voucher batch");
  return i;
};

export async function mockGetVoucherBatches(): Promise<VoucherBatches> { await wait(150); return { items: batches.map((b) => ({ ...b })), voucherValuesKobo: VALUES, maxCards: 240 }; }
export async function mockRequestBatch(input: { faceValueKobo: number; cardCount: number; reason: string }): Promise<void> {
  await wait(400);
  const next = Math.max(0, ...batches.map((b) => b.batchId)) + 1;
  const b = batch(next, input.faceValueKobo, input.cardCount, "requested", 0);
  batches.unshift(b);
  log("Voucher batch requested", `${b.name}, ${b.cardCount} cards: ${input.reason}`);
}
export async function mockAdvanceBatch(batchId: number, to: "approved" | "in_stock" | "on_sale"): Promise<void> {
  await wait(300);
  const i = find(batchId);
  const step = NEXT_BATCH_STEP[batches[i].state];
  if (batches[i].state === to) return;
  if (!step || step.kind !== "advance" || step.to !== to) throw new ApiError(409, "voucher_step_refused", `A batch that is ${batches[i].state} cannot move to ${to}`);
  batches[i] = { ...batches[i], state: to, approvedBy: to === "approved" ? ACTOR : batches[i].approvedBy };
  log(`Voucher batch moved to ${to}`, batches[i].name);
}
// Mock mode has no PINs: the "sheet" is a one-line placeholder, so a demo on mock data never hands out anything usable.
export async function mockPrintBatch(batchId: number): Promise<Blob> {
  await wait(500);
  const i = find(batchId);
  if (batches[i].state !== "approved") throw new ApiError(409, "voucher_step_refused", "Only an approved batch can be printed, and only once");
  batches[i] = { ...batches[i], state: "sent_to_printer", printedBy: ACTOR, printedAt: nowSec() };
  log("Voucher batch printed", batches[i].name);
  return new Blob(["Mock data: no real cards or PINs."], { type: "application/pdf" });
}
export async function mockLockBatch(batchId: number, reason: string): Promise<void> {
  await wait(300);
  const i = find(batchId);
  if (batches[i].state === "locked") throw new ApiError(409, "voucher_step_refused", "The batch is locked already");
  batches[i] = { ...batches[i], state: "locked" };
  log("Voucher batch locked", `${batches[i].name}: ${reason}`);
}
export async function mockLookupCard(cardNumber: string): Promise<VoucherCard> {
  await wait(300);
  const c = cards.find((x) => x.number === cardNumber.replace(/\D/g, ""));
  if (!c) throw new ApiError(404, "not_found", "No voucher with that card number");
  return toCard(c);
}
export async function mockLockCard(voucherId: number, reason: string): Promise<void> {
  await wait(400);
  const c = cards.find((x) => x.voucherId === voucherId);
  if (!c) throw new ApiError(404, "not_found", "No such card");
  if (c.state === "used" || c.state === "expired" || c.state === "locked") throw new ApiError(409, "voucher_step_refused", `A ${c.state} card cannot be locked`);
  c.state = "locked";
  log("Voucher card locked", `•••• ${c.number.slice(-4)}: ${reason}`);
}
