import { ApiError } from "../../lib/api";
import { mockFindLine } from "../lines/mock";
import type { CallRecord, HistoryEntry, LineDetail, UsagePage } from "./types";

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));
// small deterministic random numbers, so the same line always shows the same data
const rng = (seed: number) => () => {
  seed = (seed + 0x6d2b79f5) | 0;
  let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
  t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
};
const PLANS: Record<string, { total: number; ul: number; dl: number }> = {
  "Weekly 2GB": { total: 2e9, ul: 10, dl: 20 }, "Starter 5GB": { total: 5e9, ul: 10, dl: 20 }, "Family 20GB": { total: 20e9, ul: 20, dl: 40 },
};
const num = (imsi: string) => Number(imsi.slice(-3));
const nowSec = () => Math.floor(Date.now() / 1000);

function need(key: string) {
  const line = mockFindLine(key);
  if (!line) throw new ApiError(404, "line_not_found", "No such line");
  return line;
}

export async function mockGetLine(key: string): Promise<LineDetail> {
  await wait(250);
  const l = need(key), n = num(l.imsi), r = rng(n), p = PLANS[l.planName] ?? PLANS["Starter 5GB"];
  const used = l.state === "out_of_data" ? p.total : l.state === "awaiting_activation" ? 0 : Math.round(p.total * (0.1 + r() * 0.75));
  return {
    lineId: l.lineId, planId: l.planId, imsi: l.imsi, iccid: l.iccid, msisdn: l.msisdn, state: l.state, customerId: `c-${n}`, customerName: l.customerName, planName: l.planName, planEndsEpoch: l.planEndsEpoch,
    allowanceTotalBytes: p.total, allowanceUsedBytes: used, speedUlMbps: p.ul, speedDlMbps: p.dl,
    staticIp: l.state === "awaiting_activation" ? null : `10.45.${Math.floor(n / 250)}.${(n % 250) + 2}`,
    provisioning: l.state === "active" || l.state === "out_of_data" ? "active" : l.state === "suspended" ? "barred" : "provisioned",
    networkCheck: l.state === "awaiting_activation" ? "unknown" : "matches",
    dailyUsage: Array.from({ length: 7 }, (_, i) => ({ date: new Date(Date.now() - (6 - i) * 86400000).toISOString().slice(0, 10), bytes: Math.round((used / 7) * (0.4 + r() * 1.2)) })),
  };
}

export async function mockGetUsage(key: string, cursor: string | null): Promise<UsagePage> {
  await wait(200);
  const line = need(key);
  if (line.state === "awaiting_activation") return { items: [], nextCursor: null }; // no usage before activation
  const n = num(line.imsi), end0 = Math.floor(nowSec() / 300) * 300, total = 288, size = 10; // the last 24 hours
  const offset = cursor ? Number(cursor) : 0;
  const items = [];
  for (let i = offset; i < Math.min(offset + size, total); i++) {
    const r = rng(n * 1000 + i), end = end0 - i * 300;
    items.push({ periodStart: end - 300, periodEnd: end, bytesUp: Math.round(r() * 3_000_000), bytesDown: Math.round(r() * 30_000_000), rated: i >= 2 });
  }
  return { items, nextCursor: offset + size < total ? String(offset + size) : null };
}

export async function mockGetCalls(key: string): Promise<CallRecord[]> {
  await wait(200);
  const line = need(key);
  // PRD VOI-1..4: a deactivated (or terminated) line cannot call or be called.
  if (line.state === "awaiting_activation" || line.state === "terminated") return [];
  const n = num(line.imsi), now = nowSec();
  return Array.from({ length: 8 }, (_, i) => {
    const r = rng(n * 100 + i), start = now - 3600 * (5 + i * 7), answered = r() > 0.25, dur = Math.round(20 + r() * 420);
    return {
      callId: `call-${n}-${i}`, direction: i % 2 === 0 ? "outgoing" : "incoming", number: `+234 700 000 ${String(100 + ((n + i * 7) % 137)).padStart(4, "0")}`,
      startedAt: start, answeredAt: answered ? start + 6 : null, endedAt: answered ? start + 6 + dur : start + 25,
      qci1Bearer: answered ? "established" : "not_set_up", endReason: answered ? (i % 3 ? "Normal" : "Caller hung up") : "No answer",
    } as CallRecord;
  });
}

export async function mockGetHistory(key: string): Promise<HistoryEntry[]> {
  await wait(200);
  const l = need(key), now = nowSec(), h: HistoryEntry[] = [];
  if (l.state === "awaiting_activation") h.push({ at: now - 20 * 3600, from: null, to: "awaiting_activation", actor: "Amina Yusuf", reason: "SIM sold, waiting for KYC" });
  else {
    h.push({ at: now - 40 * 86400, from: "awaiting_activation", to: "active", actor: "Bashir Aliyu", reason: "First plan paid, KYC verified" });
    if (l.state === "out_of_data") h.push({ at: now - 5 * 3600, from: "active", to: "out_of_data", actor: "system", reason: "Allowance used up" });
    if (l.state === "expired") h.push({ at: now - 3 * 86400, from: "active", to: "expired", actor: "system", reason: "Plan validity ended without renewal" });
    if (l.state === "suspended") h.push({ at: now - 2 * 86400, from: "active", to: "suspended", actor: "Amina Yusuf", reason: "Customer request" });
  }
  return h.sort((a, b) => b.at - a.at);
}
