import { apiGet } from "../../lib/api";
import { mockGetOverview, mockGetReconciliation } from "./mock";
import type { Reconciliation, ReportsOverview } from "./types";

// ASSUMED endpoints (confirm with the RatelBSS developers; only this file should change):
//   GET /v1/reports/overview?days=14   -> ReportsOverview  (daily sales with VAT apart, revenue by plan, rated data usage, voucher redemptions)
//   GET /v1/reports/reconciliation     -> Reconciliation   (the latest nightly check of every wallet against its ledger entries)
const isMock = () => import.meta.env.VITE_USE_MOCK === "true";

export const getOverview = (days: number): Promise<ReportsOverview> => (isMock() ? mockGetOverview(days) : apiGet<ReportsOverview>(`/v1/reports/overview?days=${days}`));
export const getReconciliation = (): Promise<Reconciliation> => (isMock() ? mockGetReconciliation() : apiGet<Reconciliation>("/v1/reports/reconciliation"));
