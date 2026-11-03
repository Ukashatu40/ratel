// The lines list, the care actions and the line page's real calls, against contract-shaped bodies
// (tests/fixtures/contract, checked against contracts/openapi.yaml by tests/contract/test_desk_fixtures.py).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import customer from "./fixtures/contract/Customer.created.json";
import callList from "./fixtures/contract/CallList.json";
import history from "./fixtures/contract/LineHistory.json";
import lineActive from "./fixtures/contract/Line.active.json";
import lineList from "./fixtures/contract/LineList.json";
import planList from "./fixtures/contract/PlanList.json";
import usage from "./fixtures/contract/LineUsageList.json";
import * as detail from "../src/screens/line-detail/realApi";
import * as lines from "../src/screens/lines/realApi";

const NOW = 1794700000;
const fetchMock = vi.fn();
beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(NOW * 1000);
});
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); });

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
const calls = () => fetchMock.mock.calls.map(([url, init]) => ({ url: new URL(url as string, "http://x"), init: init as RequestInit }));

describe("the lines list", () => {
  it("asks for a page with the search and the state, and maps the rows and counts", async () => {
    fetchMock.mockResolvedValueOnce(json(200, lineList));
    const page = await lines.getLines({ q: " 0150 ", tab: "suspended", page: 2, pageSize: 10 });
    const { url } = calls()[0];
    expect(url.pathname).toBe("/v1/lines");
    expect(Object.fromEntries(url.searchParams)).toEqual({ page: "2", page_size: "10", q: "0150", state: "suspended" });
    expect(page.total).toBe(2);
    expect(page.counts).toEqual({ all: 2, awaiting_activation: 1, active: 1, out_of_data: 0, expired: 0, suspended: 0, terminated: 0 });
    expect(page.items[0]).toEqual({
      lineId: 7, planId: "1", imsi: "621000000000150", iccid: "8923400000000012345", msisdn: "2347000000150",
      customerName: "Demo Customer One", planName: "Demo Weekly", state: "active", planEndsEpoch: 1795000000,
    });
    expect(page.items[1]).toMatchObject({ state: "awaiting_activation", planEndsEpoch: null });
  });

  it("leaves the state and the search out when there are none", async () => {
    fetchMock.mockResolvedValueOnce(json(200, lineList));
    await lines.getLines({ q: "", tab: "all", page: 1, pageSize: 10 });
    expect(Object.fromEntries(calls()[0].url.searchParams)).toEqual({ page: "1", page_size: "10" });
  });
});

describe("care actions", () => {
  it.each(["suspend", "reinstate", "terminate"] as const)("%s goes to the line's own path with its reason and a key", async (kind) => {
    fetchMock.mockResolvedValueOnce(json(200, lineActive));
    await lines.careAction(kind, 7, { reason: "lost_sim", reasonText: "  phone stolen  " }, "care-key");
    const [{ url, init }] = calls();
    expect(url.pathname).toBe(`/v1/lines/7/${kind}`);
    expect(init.method).toBe("POST");
    expect((init.headers as Record<string, string>)["Idempotency-Key"]).toBe("care-key");
    expect(JSON.parse(init.body as string)).toEqual({ reason: "lost_sim", reason_text: "phone stolen" });
  });

  it("leaves the free text out when it is empty", async () => {
    fetchMock.mockResolvedValueOnce(json(200, lineActive));
    await lines.careAction("suspend", 7, { reason: "fraud", reasonText: "   " }, "k");
    expect(JSON.parse(calls()[0].init.body as string)).toEqual({ reason: "fraud" });
  });
});

describe("the line page", () => {
  const answerByPath = (extra: Record<string, unknown> = {}) =>
    fetchMock.mockImplementation((url: string) => {
      const path = new URL(url, "http://x").pathname;
      const bodies: Record<string, unknown> = {
        "/v1/lines/7": lineActive, "/v1/customers/1": customer, "/v1/plans": planList, "/v1/lines/7/usage": usage, "/v1/lines/7/history": history, ...extra,
      };
      return Promise.resolve(json(path in bodies ? 200 : 404, bodies[path] ?? { error: { code: "not_found", message: "x" } }));
    });

  it("is put together from the line, its customer, its plan and its usage", async () => {
    answerByPath();
    const line = await detail.getLine("7");
    expect(line).toMatchObject({
      lineId: 7, planId: "1", imsi: "621000000000150", msisdn: "2347000000150", state: "active", customerId: "1",
      customerName: "Demo Customer Three", // the fixture customer's name: only the name is kept
      planName: "Demo Weekly", planEndsEpoch: 1795000000, allowanceTotalBytes: 2000000000, speedUlMbps: 10, speedDlMbps: 20,
    });
    // Used is the usage since the plan started (end less 7 days = 1794395200): the old record does not count.
    expect(line.allowanceUsedBytes).toBe(30000);
    // The chart takes the last seven days, the old record included.
    expect(line.dailyUsage).toHaveLength(7);
    expect(line.dailyUsage.reduce((n, d) => n + d.bytes, 0)).toBe(30010);
    expect(line.dailyUsage.at(-1)).toEqual({ date: new Date((NOW + 3600) * 1000).toISOString().slice(0, 10), bytes: 30000 });
    // RatelLink's view is not readable from RatelBSS yet; the page says so instead of inventing it.
    expect(line).toMatchObject({ staticIp: null, provisioning: "unknown", networkCheck: "unknown" });
  });

  it("asks for usage from the plan's start (or seven days back) to now", async () => {
    answerByPath();
    await detail.getLine("7");
    const usageCall = calls().find((c) => c.url.pathname === "/v1/lines/7/usage")!;
    expect(Object.fromEntries(usageCall.url.searchParams)).toEqual({ from: String(NOW - 7 * 86400 < 1794395200 ? NOW - 7 * 86400 : 1794395200), to: String(NOW) });
  });

  it("follows the cursor until there is none", async () => {
    fetchMock.mockImplementation((url: string) => {
      const u = new URL(url, "http://x");
      if (u.pathname === "/v1/lines/7") return Promise.resolve(json(200, lineActive));
      if (u.pathname === "/v1/customers/1") return Promise.resolve(json(200, customer));
      if (u.pathname === "/v1/plans") return Promise.resolve(json(200, planList));
      if (u.searchParams.get("cursor") === "next") return Promise.resolve(json(200, { records: [usage.records[1]], next_cursor: null }));
      return Promise.resolve(json(200, { records: [usage.records[0]], next_cursor: "next" }));
    });
    const line = await detail.getLine("7");
    expect(line.allowanceUsedBytes).toBe(30000);
    expect(calls().filter((c) => c.url.pathname.endsWith("/usage"))).toHaveLength(2);
  });

  it("reads no usage before the line is activated", async () => {
    answerByPath({ "/v1/lines/7": { ...lineActive, state: "awaiting_activation", expires_at: null } });
    const line = await detail.getLine("7");
    expect(line.allowanceUsedBytes).toBe(0);
    expect(calls().some((c) => c.url.pathname.endsWith("/usage"))).toBe(false);
  });

  it("shows the last 24 hours of usage, newest first, with the cursor passed on", async () => {
    fetchMock.mockResolvedValueOnce(json(200, { ...usage, next_cursor: "older" }));
    const page = await detail.getUsage("7", "abc");
    const { url } = calls()[0];
    expect(Object.fromEntries(url.searchParams)).toEqual({ from: String(NOW - 86400), to: String(NOW), cursor: "abc" });
    expect(page.nextCursor).toBe("older");
    expect(page.items[0]).toEqual({ periodStart: 1794699600, periodEnd: 1794699900, bytesUp: 1000, bytesDown: 9000, rated: false });
  });

  it("reads the history as the audit trail", async () => {
    fetchMock.mockResolvedValueOnce(json(200, history));
    const entries = await detail.getHistory("7");
    expect(calls()[0].url.pathname).toBe("/v1/lines/7/history");
    expect(entries[0]).toEqual({ at: 1794690000, from: "active", to: "suspended", actor: "staff:2", reason: "customer_request: asked at the counter" });
  });

  it("reads the last 30 days of calls and tells outgoing from incoming by the line's own number", async () => {
    fetchMock.mockResolvedValueOnce(json(200, { ...callList, next_cursor: "older" }));
    const page = await detail.getCalls("7", "2347000000150", "abc");
    const { url } = calls()[0];
    expect(url.pathname).toBe("/v1/lines/7/calls");
    expect(Object.fromEntries(url.searchParams)).toEqual({ from: String(NOW - 30 * 86400), to: String(NOW), cursor: "abc" });
    expect(page.nextCursor).toBe("older");
    // 1st: someone rang the line and it was not answered. 2nd: the line rang out and was answered. 3rd: the line hung up first.
    expect(page.items[0]).toEqual({ callId: "fx-call-003", direction: "incoming", number: "2347000000151", startedAt: NOW - 600, answeredAt: null, endedAt: NOW - 575, endReason: "not_answered" });
    expect(page.items[1]).toMatchObject({ direction: "outgoing", number: "2347000000151", answeredAt: NOW - 3594, endReason: "completed" });
    expect(page.items[2]).toMatchObject({ direction: "outgoing", number: "2347000000152", answeredAt: null, endReason: "cancelled" });
  });

  it("asks for no cursor on the first page", async () => {
    fetchMock.mockResolvedValueOnce(json(200, callList));
    await detail.getCalls("7", "2347000000150", null);
    expect(calls()[0].url.searchParams.has("cursor")).toBe(false);
  });

  it("refuses a line key that is not a whole number before asking the API", async () => {
    await expect(detail.getLine("621000000000150x")).rejects.toThrow(/valid id/);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
