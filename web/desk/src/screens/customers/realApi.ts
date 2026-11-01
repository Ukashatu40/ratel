import { apiGet, apiPost } from "../../lib/api";
import { wireId } from "../sell-sim/contract";
import type { Customer } from "../sell-sim/types";
import { customerFromWire, customerHistoryFromWire, customersPageFromWire, toWireKyc, type WireCustomer, type WireCustomerHistory, type WireCustomerList } from "./contract";
import type { CustomerHistoryEntry, CustomersPage, CustomersQuery, KycDecision } from "./types";

// The real calls of the customers screens, to the paths and shapes of contracts/openapi.yaml.
export const getCustomers = (query: CustomersQuery): Promise<CustomersPage> => {
  const params = new URLSearchParams({ page: String(query.page), page_size: String(query.pageSize) });
  if (query.q.trim()) params.set("q", query.q.trim());
  if (query.tab !== "all") params.set("kyc_status", query.tab);
  return apiGet<WireCustomerList>(`/v1/customers?${params}`).then(customersPageFromWire);
};

export const getCustomer = async (id: string): Promise<Customer> =>
  customerFromWire(await apiGet<WireCustomer>(`/v1/customers/${wireId(id)}`)); // a bad id rejects, it does not throw

export const getCustomerHistory = async (id: string): Promise<CustomerHistoryEntry[]> =>
  customerHistoryFromWire(await apiGet<WireCustomerHistory>(`/v1/customers/${wireId(id)}/history?page=1&page_size=200`));

// Only an admin may decide; an agent gets 403. Deciding what the customer already is changes nothing.
export const setKyc = async (id: string, decision: KycDecision, idempotencyKey: string): Promise<void> => {
  await apiPost<WireCustomer>(`/v1/customers/${wireId(id)}/kyc`, toWireKyc(decision), idempotencyKey);
};
