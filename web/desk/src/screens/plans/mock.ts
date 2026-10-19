import { ApiError } from "../../lib/api";
import { formatNaira } from "../../lib/format";
import { mockPlans } from "../sell-sim/mock";
import type { Bundle, BundleInput, Kind, OfferHistoryEntry, PlanFull, PlanInput } from "./types";

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));
const nowSec = () => Math.floor(Date.now() / 1000);
const BOTH = ["RatelDesk", "RatelPay"];

const plans: PlanFull[] = [
  ...mockPlans.map((p) => ({ ...p, channels: BOTH, status: "on_sale" as const })),
  { planId: "p4", name: "Promo 1GB", priceKobo: 50_000, validityDays: 3, dataBytes: 1_000_000_000, speedUlMbps: 5, speedDlMbps: 10, onExhaustion: "stop", slowUlMbps: 0, slowDlMbps: 0, channels: ["RatelDesk"], status: "retired" },
];
const bundles: Bundle[] = [
  { bundleId: "b1", name: "Top-up 1GB", priceKobo: 70_000, validityDays: 7, dataBytes: 1_000_000_000, channels: BOTH, status: "on_sale" },
  { bundleId: "b2", name: "Top-up 3GB", priceKobo: 180_000, validityDays: 14, dataBytes: 3_000_000_000, channels: BOTH, status: "on_sale" },
];

// Sell SIM reads the same list: keep its on-sale plans in step with this catalog.
function syncSellSim() {
  mockPlans.splice(0, mockPlans.length, ...plans.filter((p) => p.status === "on_sale").map((p) => ({
    planId: p.planId, name: p.name, priceKobo: p.priceKobo, validityDays: p.validityDays, dataBytes: p.dataBytes, speedUlMbps: p.speedUlMbps, speedDlMbps: p.speedDlMbps,
    onExhaustion: p.onExhaustion, slowUlMbps: p.slowUlMbps, slowDlMbps: p.slowDlMbps,
  })));
}

const hist = new Map<string, OfferHistoryEntry[]>();
const log = (key: string, action: string, detail = "") => hist.set(key, [...(hist.get(key) ?? []), { at: nowSec(), action, actor: "Amina Yusuf", detail }]);
plans.forEach((p) => hist.set(`plan:${p.planId}`, [{ at: nowSec() - 86400 * 30, action: "Plan created", actor: "Ibrahim Danladi", detail: "" }]));
bundles.forEach((b) => hist.set(`bundle:${b.bundleId}`, [{ at: nowSec() - 86400 * 30, action: "Bundle created", actor: "Ibrahim Danladi", detail: "" }]));

const gb = (bytes: number) => `${bytes / 1e9} GB`;
function diff(a: BundleInput, b: BundleInput): string[] {
  const out: string[] = [];
  if (a.name !== b.name) out.push(`Name "${a.name}" to "${b.name}"`);
  if (a.priceKobo !== b.priceKobo) out.push(`Price ${formatNaira(a.priceKobo)} to ${formatNaira(b.priceKobo)}`);
  if (a.validityDays !== b.validityDays) out.push(`Validity ${a.validityDays} to ${b.validityDays} days`);
  if (a.dataBytes !== b.dataBytes) out.push(`Data ${gb(a.dataBytes)} to ${gb(b.dataBytes)}`);
  if (a.channels.join() !== b.channels.join()) out.push(`Channels ${a.channels.join(", ")} to ${b.channels.join(", ")}`);
  return out;
}
function planDiff(a: PlanInput, b: PlanInput): string[] {
  const out = diff(a, b);
  if (a.speedUlMbps !== b.speedUlMbps || a.speedDlMbps !== b.speedDlMbps) out.push(`Speed ${a.speedUlMbps}/${a.speedDlMbps} to ${b.speedUlMbps}/${b.speedDlMbps} Mbps`);
  if (a.onExhaustion !== b.onExhaustion) out.push(`When data runs out: ${a.onExhaustion} to ${b.onExhaustion}`);
  if (a.slowUlMbps !== b.slowUlMbps || a.slowDlMbps !== b.slowDlMbps) out.push(`Slow speed ${a.slowUlMbps}/${a.slowDlMbps} to ${b.slowUlMbps}/${b.slowDlMbps} Mbps`);
  return out;
}

export async function mockGetPlans(): Promise<PlanFull[]> { await wait(200); return plans.map((p) => ({ ...p })); }
export async function mockGetBundles(): Promise<Bundle[]> { await wait(200); return bundles.map((b) => ({ ...b })); }

export async function mockSavePlan(id: string | null, input: PlanInput): Promise<void> {
  await wait(400);
  if (id === null) {
    const p: PlanFull = { ...input, planId: `p${plans.length + 1}`, status: "on_sale" };
    plans.push(p); log(`plan:${p.planId}`, "Plan created");
  } else {
    const i = plans.findIndex((p) => p.planId === id);
    if (i < 0) throw new ApiError(404, "plan_not_found", "No such plan");
    if (plans[i].status === "retired") throw new Error("A retired plan cannot be edited");
    log(`plan:${id}`, "Plan edited", planDiff(plans[i], input).join("; ") || "No field changed");
    plans[i] = { ...plans[i], ...input };
  }
  syncSellSim();
}

export async function mockSaveBundle(id: string | null, input: BundleInput): Promise<void> {
  await wait(400);
  if (id === null) {
    const b: Bundle = { ...input, bundleId: `b${bundles.length + 1}`, status: "on_sale" };
    bundles.push(b); log(`bundle:${b.bundleId}`, "Bundle created");
  } else {
    const i = bundles.findIndex((b) => b.bundleId === id);
    if (i < 0) throw new ApiError(404, "bundle_not_found", "No such bundle");
    if (bundles[i].status === "retired") throw new Error("A retired bundle cannot be edited");
    log(`bundle:${id}`, "Bundle edited", diff(bundles[i], input).join("; ") || "No field changed");
    bundles[i] = { ...bundles[i], ...input };
  }
}

export async function mockRetire(kind: Kind, id: string): Promise<void> {
  await wait(400);
  if (kind === "plan") {
    const i = plans.findIndex((p) => p.planId === id);
    if (i < 0) throw new ApiError(404, "plan_not_found", "No such plan");
    plans[i] = { ...plans[i], status: "retired" }; log(`plan:${id}`, "Plan retired"); syncSellSim();
  } else {
    const i = bundles.findIndex((b) => b.bundleId === id);
    if (i < 0) throw new ApiError(404, "bundle_not_found", "No such bundle");
    bundles[i] = { ...bundles[i], status: "retired" }; log(`bundle:${id}`, "Bundle retired");
  }
}

export async function mockOfferHistory(kind: Kind, id: string): Promise<OfferHistoryEntry[]> {
  await wait(150);
  return [...(hist.get(`${kind}:${id}`) ?? [])].sort((a, b) => b.at - a.at);
}
