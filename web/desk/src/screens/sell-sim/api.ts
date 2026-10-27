import { apiGet, apiPost } from "../../lib/api";
import { mockActivate, mockCreateCustomer, mockNumbers, mockPlans, mockSearchCustomers, mockSims } from "./mock";
import type { ActivateRequest, ActivateResult, Customer, FreeSim, NewCustomer, Plan } from "./types";

// With VITE_USE_MOCK=true these return fixture data. The real endpoints below are ASSUMED from the Build Plan
// (/v1/customers, /v1/stock, /v1/plans, /v1/lines). Confirm shapes with the RatelBSS developers; only this file should change.
const isMock = () => import.meta.env.MODE === "test" || import.meta.env.VITE_USE_MOCK === "true";

export const searchCustomers = (q: string): Promise<Customer[]> =>
  isMock() ? mockSearchCustomers(q) : apiGet<{ items: Customer[] }>(`/v1/customers?q=${encodeURIComponent(q)}&pageSize=8`).then((r) => r.items);

export const createCustomer = (input: NewCustomer): Promise<Customer> =>
  isMock() ? mockCreateCustomer(input) : apiPost<Customer>("/v1/customers", input);

export const getFreeSims = (): Promise<FreeSim[]> =>
  isMock() ? Promise.resolve(mockSims) : apiGet<FreeSim[]>("/v1/stock/sims?state=in_stock");

export const getAvailableNumbers = (): Promise<string[]> =>
  isMock() ? Promise.resolve(mockNumbers) : apiGet<{ items: { msisdn: string }[] }>("/v1/stock/numbers?state=available&pageSize=200").then((r) => r.items.map((i) => i.msisdn));

export const getPlansOnSale = (): Promise<Plan[]> =>
  isMock() ? Promise.resolve(mockPlans) : apiGet<Plan[]>("/v1/plans?status=on_sale");

// One activation request per sale. The Idempotency-Key makes a retry safe.
// TODO(PRD): how the first plan is paid for at the counter (voucher, wallet, card) is not defined yet.
export const activateLine = (req: ActivateRequest, idempotencyKey: string): Promise<ActivateResult> =>
  isMock() ? mockActivate(req) : apiPost<ActivateResult>("/v1/lines", req, idempotencyKey);
