import type { Customer } from "../sell-sim/types";
import * as mock from "./mock";
import * as real from "./realApi";
import type { CustomerHistoryEntry, CustomersPage, CustomersQuery, KycDecision } from "./types";

// With VITE_USE_MOCK=true these return fixture data. Otherwise they call the API (realApi.ts, contract.ts).
const isMock = () => import.meta.env.MODE === "test" || import.meta.env.VITE_USE_MOCK === "true";

export const getCustomers = (query: CustomersQuery): Promise<CustomersPage> => (isMock() ? mock.mockGetCustomers(query) : real.getCustomers(query));
export const getCustomer = (id: string): Promise<Customer> => (isMock() ? mock.mockGetCustomer(id) : real.getCustomer(id));
export const getCustomerHistory = (id: string): Promise<CustomerHistoryEntry[]> => (isMock() ? mock.mockGetCustomerHistory(id) : real.getCustomerHistory(id));
export const setKyc = (id: string, decision: KycDecision, idempotencyKey: string): Promise<void> =>
  isMock() ? mock.mockSetKyc(id, decision) : real.setKyc(id, decision, idempotencyKey);
