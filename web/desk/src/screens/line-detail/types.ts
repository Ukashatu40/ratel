import type { LineState } from "../dashboard/types";

export interface LineDetail {
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
  provisioning: "provisioned" | "active" | "barred"; // what RatelLink reports
  networkCheck: "matches" | "mismatch" | "unknown";   // does the BSS view match the network?
  dailyUsage: { date: string; bytes: number }[];       // last 7 days, oldest first, date as YYYY-MM-DD
}

export interface UsageRecord { periodStart: number; periodEnd: number; bytesUp: number; bytesDown: number; rated: boolean; source: string }
export interface UsagePage { items: UsageRecord[]; total: number }

export interface CallRecord {
  callId: string;
  direction: "outgoing" | "incoming";
  number: string;                      // the other party
  startedAt: number;
  answeredAt: number | null;           // null = never answered
  endedAt: number;
  qci1Bearer: "established" | "not_set_up";
  endReason: string;
}

export interface HistoryEntry { at: number; from: LineState | null; to: LineState; actor: string; reason: string }