import { ApiError } from "../../lib/api";
import { NEXT_BATCH_STEP } from "./types";
import type { BatchState, NumberRow, NumbersPage, NumbersQuery, SimBatch, SimImportRow, SimSummary, StockHistoryEntry, VoucherBatch, VoucherCard, VoucherState } from "./types";

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));
const nowSec = () => Math.floor(Date.now() / 1000);
const ACTOR = "Amina Yusuf";

// ---- history (every stock change is recorded)
const history: StockHistoryEntry[] = [
  { at: nowSec() - 2 * 86400, action: "SIM batch imported", actor: "Ibrahim Danladi", detail: "SIM-2026-007, 2,000 SIMs" },
  { at: nowSec() - 3 * 3600, action: "Voucher batch approved", actor: "Ibrahim Danladi", detail: "B-2026-015" },
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
  if (i % 9 === 0) return { msisdn, state: "quarantined" as const, availableFromEpoch: nowSec() + ((i % 10) + 1) * 86400 };
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
const batches: VoucherBatch[] = [
  { batchId: "B-2026-014", faceValueKobo: 100_000, cardCount: 2000, state: "in_stock", createdBy: "Amina Yusuf", createdAt: nowSec() - 6 * 86400 },
  { batchId: "B-2026-015", faceValueKobo: 50_000, cardCount: 1000, state: "approved", createdBy: "Bashir Aliyu", createdAt: nowSec() - 86400 },
  { batchId: "B-2026-013", faceValueKobo: 200_000, cardCount: 1500, state: "on_sale", createdBy: "Amina Yusuf", createdAt: nowSec() - 20 * 86400 },
  { batchId: "B-2026-009", faceValueKobo: 50_000, cardCount: 3000, state: "expired", createdBy: "Bashir Aliyu", createdAt: nowSec() - 120 * 86400 },
];
interface Card { voucherId: string; number: string; batchId: string; faceValueKobo: number; state: VoucherState; failedAttempts: number; checkDigitValid: boolean; redeemedBy: string | null; redeemedAt: number | null }
// Sample cards to try in the lookup (card numbers have 20 digits).
const cards: Card[] = [
  { voucherId: "v1", number: "10000000000000004821", batchId: "B-2026-014", faceValueKobo: 100_000, state: "locked", failedAttempts: 5, checkDigitValid: true, redeemedBy: null, redeemedAt: null },
  { voucherId: "v2", number: "10000000000000001111", batchId: "B-2026-014", faceValueKobo: 100_000, state: "in_stock", failedAttempts: 0, checkDigitValid: true, redeemedBy: null, redeemedAt: null },
  { voucherId: "v3", number: "10000000000000002222", batchId: "B-2026-013", faceValueKobo: 200_000, state: "on_sale", failedAttempts: 3, checkDigitValid: true, redeemedBy: null, redeemedAt: null },
  { voucherId: "v4", number: "10000000000000003333", batchId: "B-2026-013", faceValueKobo: 200_000, state: "used", failedAttempts: 0, checkDigitValid: true, redeemedBy: "+234 700 000 0101", redeemedAt: nowSec() - 3 * 86400 },
];
const toCard = (c: Card): VoucherCard => ({ voucherId: c.voucherId, maskedNumber: `•••• •••• •••• •••• ${c.number.slice(-4)}`, batchId: c.batchId, faceValueKobo: c.faceValueKobo, state: c.state, failedAttempts: c.failedAttempts, maxAttempts: 5, checkDigitValid: c.checkDigitValid, redeemedBy: c.redeemedBy, redeemedAt: c.redeemedAt });

export async function mockGetVoucherBatches(): Promise<VoucherBatch[]> { await wait(150); return batches.map((b) => ({ ...b })); }
export async function mockRequestBatch(input: { faceValueKobo: number; cardCount: number }): Promise<void> {
  await wait(400);
  const next = Math.max(...batches.map((b) => Number(b.batchId.slice(-3)))) + 1;
  const b: VoucherBatch = { batchId: `B-2026-${String(next).padStart(3, "0")}`, ...input, state: "requested", createdBy: ACTOR, createdAt: nowSec() };
  batches.unshift(b);
  log("Voucher batch requested", `${b.batchId}, ${b.cardCount} cards`);
}
export async function mockAdvanceBatch(batchId: string): Promise<void> {
  await wait(300);
  const i = batches.findIndex((b) => b.batchId === batchId);
  if (i < 0) throw new ApiError(404, "batch_not_found", "No such batch");
  const steps: BatchState[] = ["requested", "approved", "sent_to_printer", "in_stock", "on_sale"];
  const at = steps.indexOf(batches[i].state);
  if (!NEXT_BATCH_STEP[batches[i].state] || at < 0) throw new Error("This batch cannot move forward");
  batches[i] = { ...batches[i], state: steps[at + 1] };
  log(`Voucher batch moved to ${steps[at + 1]}`, batchId);
}
export async function mockLookupCard(cardNumber: string): Promise<VoucherCard> {
  await wait(300);
  const c = cards.find((x) => x.number === cardNumber.replace(/\D/g, ""));
  if (!c) throw new ApiError(404, "voucher_not_found", "No voucher with that card number");
  return toCard(c);
}
export async function mockLockCard(voucherId: string, reason: string): Promise<void> {
  await wait(400);
  const c = cards.find((x) => x.voucherId === voucherId);
  if (!c) throw new ApiError(404, "voucher_not_found", "No such voucher");
  if (c.state === "used" || c.state === "expired" || c.state === "locked") throw new Error("This card cannot be locked: it is already used, expired or locked");
  c.state = "locked";
  log("Voucher card locked", `•••• ${c.number.slice(-4)}: ${reason}`);
}
