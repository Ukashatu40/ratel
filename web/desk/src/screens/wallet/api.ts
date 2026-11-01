import * as mock from "./mock";
import * as real from "./realApi";
import type { LedgerPage, LedgerQuery, LineWallet, WalletSummary } from "./types";

// With VITE_USE_MOCK=true these return fixture data. Otherwise they call the API (realApi.ts, contract.ts).
const isMock = () => import.meta.env.MODE === "test" || import.meta.env.VITE_USE_MOCK === "true";

export const getWalletSummary = (): Promise<WalletSummary> => (isMock() ? mock.mockGetWalletSummary() : real.getWalletSummary());
export const getLedger = (q: LedgerQuery): Promise<LedgerPage> => (isMock() ? mock.mockGetLedger(q) : real.getLedger(q));
export const getLineWallet = (key: string): Promise<LineWallet> => (isMock() ? mock.mockGetWallet(key) : real.getLineWallet(key));
