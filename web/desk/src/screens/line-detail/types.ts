import type { LineState } from "../dashboard/types";

export interface LineDetail {
  lineId: number;
  planId: string;
  imsi: string;
  iccid: string;
  msisdn: string;
  state: LineState;
  customerId: string;
  customerName: string;
  planName: string;
  planEndsEpoch: number | null;       // Unix seconds, UTC
  allowanceTotalBytes: number;
  allowanceUsedBytes: number;
  speedUlMbps: number;
  speedDlMbps: number;
  staticIp: string | null;            // null until the line is activated
  provisioning: "provisioned" | "active" | "barred" | "unknown"; // what RatelLink reports; "unknown" until RatelBSS can read it (TODO(contract))
  networkCheck: "matches" | "mismatch" | "unknown";   // does the BSS view match the network? TODO(contract): no operation gives it yet
  dailyUsage: { date: string; bytes: number }[];       // last 7 days, oldest first, date as YYYY-MM-DD
}

export interface UsageRecord { periodStart: number; periodEnd: number; bytesUp: number; bytesDown: number; rated: boolean }
// Newest first. nextCursor is opaque: send it back unchanged to get the older records.
export interface UsagePage { items: UsageRecord[]; nextCursor: string | null }

// How a call ended. The set is the call record agreement's proposal (docs/call-record-agreement.md, section 11).
// TODO(PRD): decision 8 may change it; the labels are in CallsTab.tsx.
export type EndReason = "completed" | "cancelled" | "declined" | "not_answered" | "unavailable" | "failed";

export interface CallRecord {
  callId: string;
  direction: "outgoing" | "incoming";  // from the line's own number: it is the caller or the callee
  number: string;                      // the other party, as stored (234 and ten digits when the agent knew the form)
  startedAt: number;                   // the INVITE arrived: the ring time is answeredAt (or endedAt) less this
  answeredAt: number | null;           // null = never answered
  endedAt: number;
  endReason: EndReason;
}

export interface CallsPage { items: CallRecord[]; nextCursor: string | null }

export interface HistoryEntry { at: number; from: LineState | null; to: LineState; actor: string; reason: string }
