// The customers screens' real calls, against contract-shaped bodies (tests/fixtures/contract, checked against
// contracts/openapi.yaml by tests/contract/test_desk_fixtures.py).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import customer from "./fixtures/contract/Customer.created.json";
import customerList from "./fixtures/contract/CustomerList.json";
import history from "./fixtures/contract/CustomerHistory.json";
import * as real from "../src/screens/customers/realApi";
import { kycMovesFrom } from "../src/screens/customers/types";

const fetchMock = vi.fn();
beforeEach(() => { fetchMock.mockReset(); vi.stubGlobal("fetch", fetchMock); });
afterEach(() => { vi.unstubAllGlobals(); });
const answer = (status: number, body: unknown) =>
  fetchMock.mockResolvedValueOnce(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
const call = () => {
  const [url, init] = fetchMock.mock.calls.at(-1)! as [string, RequestInit];
  return { url: new URL(url, "http://x"), init, headers: init.headers as Record<string, string> };
};

describe("customers", () => {
  it("lists a page with the search and the KYC filter, and a row carries no NIN or address", async () => {
    answer(200, customerList);
    const page = await real.getCustomers({ q: " demo ", tab: "pending", page: 3, pageSize: 10 });
    expect(call().url.pathname).toBe("/v1/customers");
    expect(Object.fromEntries(call().url.searchParams)).toEqual({ page: "3", page_size: "10", q: "demo", kyc_status: "pending" });
    expect(page.total).toBe(2);
    expect(page.counts).toEqual({ all: 2, pending: 1, verified: 1, rejected: 0 });
    expect(page.items[0]).toMatchObject({ id: "1", name: "Demo Customer One", kycStatus: "verified", linesCount: 0, idNumber: "", address: "" });
    expect(page.items[1]).toMatchObject({ id: "2", kycStatus: "pending", blocked: true, linesCount: 1 });
  });

  it("leaves the filter and the search out when there are none", async () => {
    answer(200, customerList);
    await real.getCustomers({ q: "", tab: "all", page: 1, pageSize: 10 });
    expect(Object.fromEntries(call().url.searchParams)).toEqual({ page: "1", page_size: "10" });
  });

  it("opens one customer, with the NIN and the address", async () => {
    answer(200, customer);
    const c = await real.getCustomer("3");
    expect(call().url.pathname).toBe("/v1/customers/3");
    expect(c).toMatchObject({ id: "3", idType: "NIN", idNumber: "00000000003", address: "1 Demo Road", kycStatus: "pending" });
  });

  it("reads the history as words, newest first", async () => {
    answer(200, history);
    const entries = await real.getCustomerHistory("3");
    expect(call().url.pathname).toBe("/v1/customers/3/history");
    expect(entries.map((e) => e.action)).toEqual(["KYC verified", "Customer registered"]);
    expect(entries[0]).toMatchObject({ at: 1794690000, actor: "staff:2", reason: "Identity checked" });
  });

  it("records a KYC decision with its reason and a key", async () => {
    answer(200, { ...customer, kyc_status: "verified" });
    await real.setKyc("3", { status: "verified", reason: "  Identity checked " }, "kyc-key");
    const { url, init, headers } = call();
    expect(url.pathname).toBe("/v1/customers/3/kyc");
    expect(init.method).toBe("POST");
    expect(headers["Idempotency-Key"]).toBe("kyc-key");
    expect(JSON.parse(init.body as string)).toEqual({ status: "verified", reason: "Identity checked" });
  });

  it("refuses an id that is not a whole number before asking the API", async () => {
    await expect(real.getCustomer("c3")).rejects.toThrow(/valid id/);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("allows the moves the API allows and no others", () => {
    expect(kycMovesFrom("pending")).toEqual(["verified", "rejected"]);
    expect(kycMovesFrom("rejected")).toEqual(["verified"]);
    expect(kycMovesFrom("verified")).toEqual([]);
  });
});
