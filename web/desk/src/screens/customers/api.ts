import { apiGet, apiPost } from "../../lib/api";
import { mockGetCustomer, mockGetCustomerHistory, mockGetCustomers, mockSetKyc } from "./mock";
import type { CustomerHistoryEntry, CustomerRow, CustomersPage, CustomersQuery, KycDecision } from "./types";

// ASSUMED endpoints (confirm with the RatelBSS developers; only this file should change):
//   GET  /v1/customers?q=&kyc=&page=&pageSize=  -> { items, total, counts }
//   GET  /v1/customers/{id}                      -> CustomerRow
//   GET  /v1/customers/{id}/history              -> CustomerHistoryEntry[]
//   POST /v1/customers/{id}/kyc  { status, reason }
// Privacy question for the backend: the NIN should arrive already masked in lists, not in full.
const isMock = () => import.meta.env.VITE_USE_MOCK === "true";

export const getCustomers = (query: CustomersQuery): Promise<CustomersPage> =>
  isMock()
    ? mockGetCustomers(query)
    : apiGet<CustomersPage>(`/v1/customers?${new URLSearchParams({ q: query.q, kyc: query.tab, page: String(query.page), pageSize: String(query.pageSize) })}`);

export const getCustomer = (id: string): Promise<CustomerRow> => (isMock() ? mockGetCustomer(id) : apiGet<CustomerRow>(`/v1/customers/${id}`));

export const getCustomerHistory = (id: string): Promise<CustomerHistoryEntry[]> =>
  isMock() ? mockGetCustomerHistory(id) : apiGet<CustomerHistoryEntry[]>(`/v1/customers/${id}/history`);

export const setKyc = (id: string, decision: KycDecision, idempotencyKey: string): Promise<void> =>
  isMock() ? mockSetKyc(id, decision) : apiPost<void>(`/v1/customers/${id}/kyc`, decision, idempotencyKey);
