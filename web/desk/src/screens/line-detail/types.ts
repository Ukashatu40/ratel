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

export interface CallRecord {
  callId: string;
  direction: "outgoing" | "incoming";
  number: string;                      // the other party
  startedAt: number;
  answeredAt: number | null;           // null = never answered
  endedAt: number;
  qci1Bearer: "established" | "not_set_up"; // needs RatelVoice data (not in Contract 2)
  // TODO(PRD): allowed end_reason values and the meaning of from/to are open (decision 8).
  endReason: string;
}

export interface HistoryEntry { at: number; from: LineState | null; to: LineState; actor: string; reason: string }
