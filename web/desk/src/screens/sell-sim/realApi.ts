import { apiGet, apiPost } from "../../lib/api";
import {
  customerFromRow, customerFromWire, lineFromWire, planFromWire, purchaseFromWire, simFromWire, toWireCreateLine, toWireNewCustomer, walletFromWire, wireId,
  type WireCustomer, type WireCustomerRow, type WireLine, type WireLineWallet, type WireNumber, type WirePlan, type WirePurchase, type WireSim,
} from "./contract";
import type { CreatedLine, CreateLineRequest, Customer, FreeSim, NewCustomer, Plan, Purchase, Wallet } from "./types";

// The real calls of the sell journey, to the paths and shapes of contracts/openapi.yaml.
// The stock lists cannot be filtered by state, so the Desk asks for a page and keeps the free ones.
// TODO(contract): a state filter on /v1/stock/sims and /v1/stock/numbers, so a large stock is not cut at `limit`.
const STOCK_LIMIT = 200;

export const searchCustomers = (q: string): Promise<Customer[]> =>
  apiGet<{ customers: WireCustomerRow[] }>(`/v1/customers?${new URLSearchParams({ q, page: "1", page_size: "8" })}`).then((r) => r.customers.map(customerFromRow));

export const createCustomer = (input: NewCustomer, idempotencyKey: string): Promise<Customer> =>
  apiPost<WireCustomer>("/v1/customers", toWireNewCustomer(input), idempotencyKey).then(customerFromWire);

export const getFreeSims = (): Promise<FreeSim[]> =>
  apiGet<{ sims: WireSim[] }>(`/v1/stock/sims?limit=${STOCK_LIMIT}`).then((r) => r.sims.filter((s) => s.state === "in_stock").map(simFromWire));

export const getAvailableNumbers = (): Promise<string[]> =>
  apiGet<{ numbers: WireNumber[] }>(`/v1/stock/numbers?limit=${STOCK_LIMIT}`).then((r) => r.numbers.filter((n) => n.state === "available").map((n) => n.msisdn));

export const getPlansOnSale = (): Promise<Plan[]> =>
  apiGet<{ plans: WirePlan[] }>("/v1/plans").then((r) => r.plans.filter((p) => p.state === "on_sale").map(planFromWire));

export const createLine = async (req: CreateLineRequest, idempotencyKey: string): Promise<CreatedLine> =>
  lineFromWire(await apiPost<WireLine>("/v1/lines", toWireCreateLine(req), idempotencyKey)); // a bad id rejects, it does not throw

export const getWallet = (lineId: number): Promise<Wallet> =>
  apiGet<WireLineWallet>(`/v1/lines/${lineId}/wallet`).then(walletFromWire);

// The purchase's identity is its Idempotency-Key: a repeat returns the first purchase and debits nothing more.
export const buyPlan = async (lineId: number, planId: string, idempotencyKey: string): Promise<Purchase> =>
  purchaseFromWire(await apiPost<WirePurchase>(`/v1/lines/${lineId}/purchases`, { offer_kind: "plan", offer_id: wireId(planId) }, idempotencyKey));

// The plan's own speeds are used, so the body is empty.
export const activateLine = (lineId: number, idempotencyKey: string): Promise<CreatedLine> =>
  apiPost<WireLine>(`/v1/lines/${lineId}/activate`, {}, idempotencyKey).then(lineFromWire);

// A plan by id, whatever its state (the list gives retired plans too).
export const getPlan = (planId: string): Promise<Plan | null> =>
  apiGet<{ plans: WirePlan[] }>("/v1/plans").then((r) => r.plans.map(planFromWire).find((p) => p.planId === planId) ?? null);
