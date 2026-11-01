// The sell journey's real calls, against contract-shaped bodies (tests/fixtures/contract, checked against
// contracts/openapi.yaml by tests/contract/test_desk_fixtures.py). fetch is replaced; nothing leaves the test.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../src/lib/api";
import * as real from "../src/screens/sell-sim/realApi";
import customer from "./fixtures/contract/Customer.created.json";
import customerList from "./fixtures/contract/CustomerList.json";
import lineActive from "./fixtures/contract/Line.active.json";
import lineCreated from "./fixtures/contract/Line.created.json";
import wallet from "./fixtures/contract/LineWallet.json";
import numberList from "./fixtures/contract/NumberList.json";
import planList from "./fixtures/contract/PlanList.json";
import purchase from "./fixtures/contract/Purchase.json";
import simList from "./fixtures/contract/SimList.json";

const fetchMock = vi.fn();
beforeEach(() => { fetchMock.mockReset(); vi.stubGlobal("fetch", fetchMock); });
afterEach(() => { vi.unstubAllGlobals(); });

const answer = (status: number, body: unknown) =>
  fetchMock.mockResolvedValueOnce(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
const lastCall = () => {
  const [url, init] = fetchMock.mock.calls.at(-1)! as [string, RequestInit];
  return { url, init, headers: init.headers as Record<string, string>, body: init.body ? JSON.parse(init.body as string) : undefined };
};

describe("customers", () => {
  it("searches the list and keeps what a list row carries", async () => {
    answer(200, customerList);
    const found = await real.searchCustomers("demo");
    const { url, init } = lastCall();
    expect(url).toBe("/v1/customers?q=demo&page=1&page_size=8");
    expect(init.method).toBe("GET");
    expect(init.credentials).toBe("include");
    expect(found).toHaveLength(2);
    expect(found[0]).toMatchObject({ id: "1", name: "Demo Customer One", kycStatus: "verified", blocked: false, idNumber: "", address: "" });
    expect(found[1]).toMatchObject({ id: "2", kycStatus: "pending", blocked: true });
  });

  it("creates a customer with KYC pending, in the contract's field names, with a key", async () => {
    answer(201, customer);
    const made = await real.createCustomer(
      { name: "Demo Customer Three", phone: "+234 800 000 0003", email: "three@mail.example", idType: "NIN", idNumber: "00000000003", address: "1 Demo Road" },
      "key-1",
    );
    const { url, headers, body, init } = lastCall();
    expect(url).toBe("/v1/customers");
    expect(init.method).toBe("POST");
    expect(headers["Idempotency-Key"]).toBe("key-1");
    expect(headers["X-Ratel-Desk"]).toBe("1");
    expect(body).toEqual({ name: "Demo Customer Three", phone: "+234 800 000 0003", email: "three@mail.example", id_type: "NIN", id_number: "00000000003", address: "1 Demo Road", kyc_status: "pending" });
    expect(made).toMatchObject({ id: "3", idNumber: "00000000003", address: "1 Demo Road", kycStatus: "pending" });
  });
});

describe("stock and plans", () => {
  it("offers only SIMs that are in stock", async () => {
    answer(200, simList);
    const sims = await real.getFreeSims();
    expect(lastCall().url).toBe("/v1/stock/sims?limit=200");
    expect(sims).toEqual([{ iccid: "8923400000000012345", imsi: "621000000000150", batch: "SIM-DEMO-001" }]);
  });

  it("offers only numbers that are available, in the stored form", async () => {
    answer(200, numberList);
    expect(await real.getAvailableNumbers()).toEqual(["2347000000150", "2347000000153"]);
    expect(lastCall().url).toBe("/v1/stock/numbers?limit=200");
  });

  it("offers only plans on sale, with their ids as strings", async () => {
    answer(200, planList);
    const plans = await real.getPlansOnSale();
    expect(plans).toHaveLength(1);
    expect(plans[0]).toEqual({
      planId: "1", name: "Demo Weekly", priceKobo: 120000, validityDays: 7, dataBytes: 2000000000,
      speedUlMbps: 10, speedDlMbps: 20, onExhaustion: "slow", slowUlMbps: 0.5, slowDlMbps: 1,
    });
  });
});

describe("the sale", () => {
  it("creates the line with integer ids and the stored number", async () => {
    answer(201, lineCreated);
    const line = await real.createLine({ customerId: "1", iccid: "8923400000000012345", msisdn: "2347000000150", planId: "1" }, "sale-key");
    const { url, headers, body } = lastCall();
    expect(url).toBe("/v1/lines");
    expect(headers["Idempotency-Key"]).toBe("sale-key");
    expect(body).toEqual({ customer_id: 1, iccid: "8923400000000012345", msisdn: "2347000000150", plan_id: 1 });
    expect(line).toEqual({ lineId: 7, imsi: "621000000000150", msisdn: "2347000000150", planId: "1", state: "awaiting_activation", expiresAt: null });
  });

  it("never sends an id that is not a whole number", async () => {
    await expect(real.createLine({ customerId: "c2", iccid: "x", msisdn: "2347000000150", planId: "1" }, "k")).rejects.toThrow(/valid id/);
    await expect(real.createLine({ customerId: "1", iccid: "x", msisdn: "2347000000150", planId: "0" }, "k")).rejects.toThrow(/valid id/);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("reads the wallet of the line", async () => {
    answer(200, wallet);
    expect(await real.getWallet(7)).toEqual({ balanceKobo: 150000, ledgerSumKobo: 150000 });
    expect(lastCall().url).toBe("/v1/lines/7/wallet");
  });

  it("buys the plan with the key as its identity", async () => {
    answer(200, purchase);
    const bought = await real.buyPlan(7, "1", "buy-key");
    const { url, headers, body } = lastCall();
    expect(url).toBe("/v1/lines/7/purchases");
    expect(headers["Idempotency-Key"]).toBe("buy-key");
    expect(body).toEqual({ offer_kind: "plan", offer_id: 1 });
    expect(bought).toEqual({ priceKobo: 120000, netKobo: 111628, vatKobo: 8372, balanceKobo: 30000, validTo: 1795000000, replayed: false });
  });

  it("activates with an empty body, so the plan's own speeds apply", async () => {
    answer(200, lineActive);
    const line = await real.activateLine(7, "act-key");
    const { url, headers, body } = lastCall();
    expect(url).toBe("/v1/lines/7/activate");
    expect(headers["Idempotency-Key"]).toBe("act-key");
    expect(body).toEqual({});
    expect(line).toMatchObject({ state: "active", expiresAt: 1795000000 });
  });

  it("passes a refusal on with its status, code and words", async () => {
    answer(409, { error: { code: "insufficient_funds", message: "The wallet is short by 900.00 naira" } });
    const failure = await real.buyPlan(7, "1", "k").catch((e: unknown) => e);
    expect(failure).toBeInstanceOf(ApiError);
    expect(failure).toMatchObject({ status: 409, code: "insufficient_funds", message: "The wallet is short by 900.00 naira" });
  });
});
