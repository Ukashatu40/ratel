import * as mock from "./mock";
import * as real from "./realApi";
import type { CallsPage, HistoryEntry, LineDetail, UsagePage } from "./types";

// With VITE_USE_MOCK=true these return fixture data. Otherwise they call the API (realApi.ts, contract.ts).
// `key` is the line's id from the address. (The mock also accepts an IMSI, for the screens that still link by IMSI.)
export const isMock = () => import.meta.env.MODE === "test" || import.meta.env.VITE_USE_MOCK === "true";

export const getLine = (key: string): Promise<LineDetail> => (isMock() ? mock.mockGetLine(key) : real.getLine(key));
export const getUsage = (key: string, cursor: string | null): Promise<UsagePage> => (isMock() ? mock.mockGetUsage(key, cursor) : real.getUsage(key, cursor));
export const getHistory = (key: string): Promise<HistoryEntry[]> => (isMock() ? mock.mockGetHistory(key) : real.getHistory(key));

// `msisdn` is the line's own number (the page has it already), so the mapper can tell outgoing from incoming.
export const getCalls = (key: string, msisdn: string, cursor: string | null): Promise<CallsPage> =>
  isMock() ? mock.mockGetCalls(key, cursor) : real.getCalls(key, msisdn, cursor);
