import type { LineState } from "../dashboard/types";

export type LineTab = "all" | "active" | "out_of_data" | "suspended" | "expired";

export interface LineRow {
  imsi: string;
  iccid: string;
  msisdn: string;
  customerName: string;
  planName: string;
  state: LineState;
  planEndsEpoch: number | null; // Unix seconds, UTC. null until the line is activated
}

export interface LinesQuery { q: string; tab: LineTab; page: number; pageSize: number }
// counts are for the current search, one number per tab
export interface LinesPage { items: LineRow[]; total: number; counts: Record<LineTab, number> }