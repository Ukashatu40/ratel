import type { LineState } from "../dashboard/types";
import type { CarePayload, LineRow, LinesPage, LineTab } from "./types";

// The wire shapes of the lines list and care actions (contracts/openapi.yaml), and their mappers.
// tests/fixtures/contract/LineList.json is checked against the contract and against these mappers.

export interface WireLineRow {
  line_id: number; customer_id: number; customer_name: string; iccid: string; imsi: string; msisdn: string;
  plan_id: number; plan_name: string; state: LineState; expires_at: number | null;
}
export interface WireLineList { lines: WireLineRow[]; total: number; counts: Record<"all" | LineState, number> }

export const lineRowFromWire = (l: WireLineRow): LineRow => ({
  lineId: l.line_id, planId: String(l.plan_id), imsi: l.imsi, iccid: l.iccid, msisdn: l.msisdn,
  customerName: l.customer_name, planName: l.plan_name, state: l.state, planEndsEpoch: l.expires_at,
});

export const linesPageFromWire = (w: WireLineList): LinesPage => ({
  items: w.lines.map(lineRowFromWire), total: w.total, counts: w.counts as Record<LineTab, number>,
});

// reason_text is optional: it is left out when empty.
export const toWireCare = (p: CarePayload) => (p.reasonText.trim() ? { reason: p.reason, reason_text: p.reasonText.trim() } : { reason: p.reason });
