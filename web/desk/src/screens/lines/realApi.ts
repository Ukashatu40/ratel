import { apiGet, apiPost } from "../../lib/api";
import { wireId } from "../sell-sim/contract";
import { linesPageFromWire, toWireCare, type WireLineList } from "./contract";
import type { CareKind, CarePayload, LinesPage, LinesQuery } from "./types";

// The real calls of the lines screens, to the paths and shapes of contracts/openapi.yaml.
export const getLines = (query: LinesQuery): Promise<LinesPage> => {
  const params = new URLSearchParams({ page: String(query.page), page_size: String(query.pageSize) });
  if (query.q.trim()) params.set("q", query.q.trim());
  if (query.tab !== "all") params.set("state", query.tab);
  return apiGet<WireLineList>(`/v1/lines?${params}`).then(linesPageFromWire);
};

// suspend: active or out_of_data -> suspended. reinstate: suspended -> the state it had. terminate: final, admin only.
// A repeat with the same Idempotency-Key changes nothing.
export const careAction = async (kind: CareKind, lineId: number, payload: CarePayload, idempotencyKey: string): Promise<void> => {
  await apiPost<unknown>(`/v1/lines/${wireId(String(lineId))}/${kind}`, toWireCare(payload), idempotencyKey);
};
