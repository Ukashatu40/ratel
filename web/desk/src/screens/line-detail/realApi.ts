import { apiGet } from "../../lib/api";
import { wireId, type WireCustomer, type WireLine, type WirePlan } from "../sell-sim/contract";
import { buildLineDetail, historyFromWire, planStartOf, usageFromWire, type WireLineHistory, type WireLineUsageList, type WireUsageRecord } from "./contract";
import type { HistoryEntry, LineDetail, UsagePage } from "./types";

// The real calls of the line page, to the paths and shapes of contracts/openapi.yaml. `key` is the line's id.
const DAY = 86400;
const MAX_PAGES = 20; // 500 records a page: 10,000 records is 34 days of 5-minute intervals

const usageUrl = (id: number, from: number, to: number, cursor?: string | null) =>
  `/v1/lines/${id}/usage?${new URLSearchParams({ from: String(from), to: String(to), ...(cursor ? { cursor } : {}) })}`;

// Every usage record from `from` to `to`, newest first, following the cursor.
async function allUsage(id: number, from: number, to: number): Promise<WireUsageRecord[]> {
  const out: WireUsageRecord[] = [];
  let cursor: string | null = null;
  for (let page = 0; page < MAX_PAGES; page++) {
    const batch: WireLineUsageList = await apiGet<WireLineUsageList>(usageUrl(id, from, to, cursor));
    out.push(...batch.records);
    cursor = batch.next_cursor;
    if (!cursor) break;
  }
  return out;
}

// The line page needs four things the API keeps apart: the line, its customer's name, its plan, and its usage.
export async function getLine(key: string): Promise<LineDetail> {
  const id = wireId(key);
  const now = Math.floor(Date.now() / 1000);
  const line = await apiGet<WireLine>(`/v1/lines/${id}`);
  const [customer, plans] = await Promise.all([
    apiGet<WireCustomer>(`/v1/customers/${line.customer_id}`),
    apiGet<{ plans: WirePlan[] }>("/v1/plans"),
  ]);
  const plan = plans.plans.find((p) => p.plan_id === line.plan_id);
  const planStart = planStartOf(line, plan);
  // Before activation there is no usage. After it: the plan's whole life, and at least the last seven days for the chart.
  const usage = planStart === null ? [] : await allUsage(id, Math.min(planStart, now - 7 * DAY), now);
  return buildLineDetail(line, customer.name, plan, usage, now);
}

// The last 24 hours of 5-minute records, newest first; a cursor asks for the next older page.
export const getUsage = (key: string, cursor: string | null): Promise<UsagePage> => {
  const now = Math.floor(Date.now() / 1000);
  return apiGet<WireLineUsageList>(usageUrl(wireId(key), now - DAY, now, cursor)).then(usageFromWire);
};

export const getHistory = (key: string): Promise<HistoryEntry[]> =>
  apiGet<WireLineHistory>(`/v1/lines/${wireId(key)}/history?page=1&page_size=200`).then(historyFromWire);
