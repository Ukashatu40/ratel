import type { LineState } from "../dashboard/types";
import type { WireLine, WirePlan } from "../sell-sim/contract";
import type { CallRecord, CallsPage, EndReason, HistoryEntry, LineDetail, UsagePage, UsageRecord } from "./types";

// The wire shapes of the line page (contracts/openapi.yaml) and their mappers. The fixtures in
// tests/fixtures/contract (LineHistory, LineUsageList) are checked against the contract and against these.

export interface WireHistoryEntry { at: number; from_state: LineState; to_state: LineState; actor: string; reason: string }
export interface WireLineHistory { entries: WireHistoryEntry[]; total: number }
export interface WireUsageRecord { period_start: number; period_end: number; bytes_up: number; bytes_down: number; rated: boolean }
export interface WireLineUsageList { records: WireUsageRecord[]; next_cursor: string | null }

export interface WireCallRecord { call_id: string; from_msisdn: string; to_msisdn: string; started_at: number; answered_at: number | null; ended_at: number; end_reason: EndReason }
export interface WireCallList { records: WireCallRecord[]; next_cursor: string | null }

// The line is the caller or the callee; the record does not say which, so it is told by comparing with the line's own number.
export const callFromWire = (c: WireCallRecord, ownMsisdn: string): CallRecord => {
  const outgoing = c.from_msisdn === ownMsisdn;
  return {
    callId: c.call_id, direction: outgoing ? "outgoing" : "incoming", number: outgoing ? c.to_msisdn : c.from_msisdn,
    startedAt: c.started_at, answeredAt: c.answered_at, endedAt: c.ended_at, endReason: c.end_reason,
  };
};
export const callsFromWire = (l: WireCallList, ownMsisdn: string): CallsPage => ({ items: l.records.map((c) => callFromWire(c, ownMsisdn)), nextCursor: l.next_cursor });

export const historyFromWire = (h: WireLineHistory): HistoryEntry[] =>
  h.entries.map((e) => ({ at: e.at, from: e.from_state, to: e.to_state, actor: e.actor, reason: e.reason }));

export const usageRecordFromWire = (r: WireUsageRecord): UsageRecord => ({
  periodStart: r.period_start, periodEnd: r.period_end, bytesUp: r.bytes_up, bytesDown: r.bytes_down, rated: r.rated,
});
export const usageFromWire = (u: WireLineUsageList): UsagePage => ({ items: u.records.map(usageRecordFromWire), nextCursor: u.next_cursor });

const DAY = 86400;
const WAT_OFFSET = 3600; // West Africa Time is UTC+1 all year: a day for the page is a WAT day
const watDate = (epoch: number) => new Date((epoch + WAT_OFFSET) * 1000).toISOString().slice(0, 10);

// When the plan started: its end less its length. null before the line is activated.
export const planStartOf = (line: WireLine, plan: WirePlan | undefined): number | null =>
  line.expires_at != null && plan ? line.expires_at - plan.validity_days * DAY : null;

// The line page from what the API gives: the line, its customer's name, its plan and its usage records.
// The contract has no "allowance left", so "used" is the usage since the plan started (an estimate; TODO(contract)).
// RatelLink's view of the line (static address, provisioning, network check) is not readable from RatelBSS yet.
export function buildLineDetail(line: WireLine, customerName: string, plan: WirePlan | undefined, usage: WireUsageRecord[], now: number): LineDetail {
  const start = planStartOf(line, plan);
  const since = start ?? 0;
  const used = usage.filter((r) => r.period_start >= since).reduce((sum, r) => sum + r.bytes_up + r.bytes_down, 0);
  const perDay = new Map<string, number>();
  usage.forEach((r) => perDay.set(watDate(r.period_start), (perDay.get(watDate(r.period_start)) ?? 0) + r.bytes_up + r.bytes_down));
  return {
    lineId: line.line_id, planId: String(line.plan_id), imsi: line.imsi, iccid: line.iccid, msisdn: line.msisdn, state: line.state,
    customerId: String(line.customer_id), customerName, planName: plan?.name ?? `Plan ${line.plan_id}`, planEndsEpoch: line.expires_at ?? null,
    allowanceTotalBytes: plan?.data_bytes ?? 0, allowanceUsedBytes: used,
    speedUlMbps: plan?.speed_ul_mbps ?? 0, speedDlMbps: plan?.speed_dl_mbps ?? 0,
    staticIp: null, provisioning: "unknown", networkCheck: "unknown",
    dailyUsage: Array.from({ length: 7 }, (_, i) => {
      const date = watDate(now - (6 - i) * DAY);
      return { date, bytes: perDay.get(date) ?? 0 };
    }),
  };
}
