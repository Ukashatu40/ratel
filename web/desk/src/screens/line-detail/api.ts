import * as mock from "./mock";
import * as real from "./realApi";
import type { CallRecord, HistoryEntry, LineDetail, UsagePage } from "./types";

// With VITE_USE_MOCK=true these return fixture data. Otherwise they call the API (realApi.ts, contract.ts).
// `key` is the line's id from the address. (The mock also accepts an IMSI, for the screens that still link by IMSI.)
export const isMock = () => import.meta.env.MODE === "test" || import.meta.env.VITE_USE_MOCK === "true";

export const getLine = (key: string): Promise<LineDetail> => (isMock() ? mock.mockGetLine(key) : real.getLine(key));
export const getUsage = (key: string, cursor: string | null): Promise<UsagePage> => (isMock() ? mock.mockGetUsage(key, cursor) : real.getUsage(key, cursor));
export const getHistory = (key: string): Promise<HistoryEntry[]> => (isMock() ? mock.mockGetHistory(key) : real.getHistory(key));

// Calls: the contract's `bss_get_line_calls` is not built (it waits for the call record agreement, #26), so the
// real mode has nothing to read yet. TODO(contract): remove `callsAvailable` when meter_get_calls exists.
export const callsAvailable = (): boolean => isMock();
export const getCalls = (key: string): Promise<CallRecord[]> => mock.mockGetCalls(key);
