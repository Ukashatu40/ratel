import * as real from "./realApi";
import * as mock from "./mock";
import type { CreatedLine, CreateLineRequest, Customer, FreeSim, NewCustomer, Plan, Purchase, Wallet } from "./types";

// With VITE_USE_MOCK=true these return fixture data. Otherwise they call the API, with the paths and shapes of
// contracts/openapi.yaml (realApi.ts and contract.ts). Only these three files know the difference.
export const isMock = () => import.meta.env.MODE === "test" || import.meta.env.VITE_USE_MOCK === "true";

export const searchCustomers = (q: string): Promise<Customer[]> => (isMock() ? mock.mockSearchCustomers(q) : real.searchCustomers(q));
export const createCustomer = (input: NewCustomer, idempotencyKey: string): Promise<Customer> =>
  isMock() ? mock.mockCreateCustomer(input) : real.createCustomer(input, idempotencyKey);
export const getFreeSims = (): Promise<FreeSim[]> => (isMock() ? Promise.resolve(mock.mockSims) : real.getFreeSims());
export const getAvailableNumbers = (): Promise<string[]> => (isMock() ? Promise.resolve(mock.mockNumbers) : real.getAvailableNumbers());
export const getPlansOnSale = (): Promise<Plan[]> => (isMock() ? Promise.resolve(mock.mockPlans) : real.getPlansOnSale());

// The sale is four calls, each safe to repeat with its Idempotency-Key: create the line, (the customer tops up at
// the RatelPay page), buy the plan from the line's wallet, activate.
// TODO(PRD): how the first plan is paid for at the counter. This is the flow the project lead chose on 2026-11-01.
export const createLine = (req: CreateLineRequest, idempotencyKey: string): Promise<CreatedLine> =>
  isMock() ? mock.mockCreateLine(req) : real.createLine(req, idempotencyKey);
export const getWallet = (lineId: number): Promise<Wallet> => (isMock() ? mock.mockGetWallet(lineId) : real.getWallet(lineId));
export const buyPlan = (lineId: number, planId: string, idempotencyKey: string): Promise<Purchase> =>
  isMock() ? mock.mockBuyPlan(lineId, planId) : real.buyPlan(lineId, planId, idempotencyKey);
export const activateLine = (lineId: number, idempotencyKey: string): Promise<CreatedLine> =>
  isMock() ? mock.mockActivateLine(lineId) : real.activateLine(lineId, idempotencyKey);
