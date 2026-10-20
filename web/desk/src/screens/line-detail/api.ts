import { apiGet } from "../../lib/api";
import { mockGetCalls, mockGetHistory, mockGetLine, mockGetUsage } from "./mock";
import type { CallRecord, HistoryEntry, LineDetail, UsagePage } from "./types";

// ASSUMED endpoints (confirm with the RatelBSS developers; only this file should change):
//   GET /v1/lines/{imsi}                      -> LineDetail
//   GET /v1/lines/{imsi}/usage?page=&pageSize= -> { items, total }   (5-minute records from RatelMeter, plus "rated")
//   GET /v1/lines/{imsi}/calls                -> CallRecord[]         (qci1Bearer is NOT in the Contract 2 call record; it needs RatelVoice data)
//   GET /v1/lines/{imsi}/history              -> HistoryEntry[]       (the append-only audit trail, ACC-3)
const isMock = () => import.meta.env.VITE_USE_MOCK === "true";

export const getLine = (imsi: string): Promise<LineDetail> => (isMock() ? mockGetLine(imsi) : apiGet<LineDetail>(`/v1/lines/${imsi}`));
export const getUsage = (imsi: string, page: number, pageSize: number): Promise<UsagePage> =>
  isMock() ? mockGetUsage(imsi, page, pageSize) : apiGet<UsagePage>(`/v1/lines/${imsi}/usage?page=${page}&pageSize=${pageSize}`);
export const getCalls = (imsi: string): Promise<CallRecord[]> => (isMock() ? mockGetCalls(imsi) : apiGet<CallRecord[]>(`/v1/lines/${imsi}/calls`));
export const getHistory = (imsi: string): Promise<HistoryEntry[]> => (isMock() ? mockGetHistory(imsi) : apiGet<HistoryEntry[]>(`/v1/lines/${imsi}/history`));