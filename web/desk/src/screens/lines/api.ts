import { apiGet, apiPost } from "../../lib/api";
import { mockGetLines, mockSuspend } from "./mock";
import type { LinesPage, LinesQuery } from "./types";

// ASSUMED endpoints (confirm with the RatelBSS developers; only this file should change):
//   GET  /v1/lines?q=&state=&page=&pageSize=   ->  { items, total, counts }
//   POST /v1/lines/{imsi}/suspend  { reason }
const isMock = () => import.meta.env.VITE_USE_MOCK === "true";

export const getLines = (query: LinesQuery): Promise<LinesPage> =>
  isMock()
    ? mockGetLines(query)
    : apiGet<LinesPage>(`/v1/lines?${new URLSearchParams({ q: query.q, state: query.tab, page: String(query.page), pageSize: String(query.pageSize) })}`);

export const suspendLine = (imsi: string, reason: string, idempotencyKey: string): Promise<void> =>
  isMock() ? mockSuspend(imsi) : apiPost<void>(`/v1/lines/${imsi}/suspend`, { reason }, idempotencyKey);