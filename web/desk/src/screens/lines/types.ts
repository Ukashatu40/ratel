import type { LineState } from "../dashboard/types";

export type LineTab = "all" | "active" | "out_of_data" | "suspended" | "expired";

// PRD decision 9 (2026-10-23): every care action carries a reason from a short fixed list plus free text.
export type CareReason = "fraud" | "non_payment" | "customer_request" | "lost_sim" | "other";
export const CARE_REASONS: CareReason[] = ["fraud", "non_payment", "customer_request", "lost_sim", "other"];
export const CARE_REASON_LABEL: Record<CareReason, string> = {
  fraud: "Fraud",
  non_payment: "Non-payment",
  customer_request: "Customer request",
  lost_sim: "Lost SIM",
  other: "Other",
};

// The wire shape accepted by POST /v1/lines/{imsi}/suspend (SuspendLineRequest in the contract).
// Both fields are required so a request cannot slip past additionalProperties: false.
export interface SuspendPayload { reason: CareReason; reason_text: string }

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
export interface LinesPage { items: LineRow[]; total: number; counts: Record<LineTab, number> }
