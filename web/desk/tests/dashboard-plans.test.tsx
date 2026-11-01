// The dashboard and plans screens against contract-shaped bodies (tests/fixtures/contract, checked against
// contracts/openapi.yaml by tests/contract/test_desk_fixtures.py).
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthContext } from "../src/lib/authContext";
import { dashboardFromWire, type WireDashboard } from "../src/screens/dashboard/contract";
import { getDashboard } from "../src/screens/dashboard/api";
import { getPlans } from "../src/screens/plans/api";
import DashboardScreen from "../src/screens/dashboard/DashboardScreen";
import PlansScreen from "../src/screens/plans/PlansScreen";
import dashboard from "./fixtures/contract/Dashboard.json";
import planList from "./fixtures/contract/PlanList.json";

const fetchMock = vi.fn();
const json = (body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } }));

// The real mode: the tests run in mock mode by default (tests/setup.ts), so switch it off for these.
const realMode = () => { vi.stubEnv("MODE", "development"); vi.stubEnv("VITE_USE_MOCK", "false"); vi.stubGlobal("fetch", fetchMock); };
beforeEach(() => fetchMock.mockReset());
afterEach(() => { vi.unstubAllEnvs(); vi.stubEnv("VITE_USE_MOCK", "true"); vi.unstubAllGlobals(); });

const wrap = (ui: React.ReactElement, entry = "/") => {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const auth = { user: { name: "Test Staff", email: "staff@example.test", role: "Super Admin" as const }, ready: true, signIn: async () => {}, signOut: async () => {} };
  return render(
    <AuthContext.Provider value={auth}><QueryClientProvider client={queryClient}><MemoryRouter initialEntries={[entry]}>{ui}</MemoryRouter></QueryClientProvider></AuthContext.Provider>,
  );
};

describe("dashboard mapping", () => {
  it("maps the API's dashboard, with no trends because the API has none", () => {
    const d = dashboardFromWire(dashboard as WireDashboard);
    expect(d.counts).toEqual({ awaiting_activation: 2, active: 8, out_of_data: 2, expired: 1, suspended: 1, terminated: 0 });
    expect(d).toMatchObject({ kycPending: 3, topupsTodayKobo: 412500, topupsYesterdayKobo: 0, trends: null });
    expect(d.topupsLast7Days.at(-1)).toEqual({ date: "2026-11-01", amountKobo: 412500 });
    expect(d.attention[0]).toEqual({ customerId: 1, lineId: 7, customerName: "Demo Customer One", msisdn: "2347000000150", issue: "out_of_data", sinceEpoch: 1794690000 });
    expect(d.attention[1]).toMatchObject({ lineId: null, msisdn: null, issue: "pending_kyc" });
  });

  it("asks GET /v1/dashboard", async () => {
    realMode();
    fetchMock.mockImplementation(() => json(dashboard));
    const d = await getDashboard();
    expect(fetchMock.mock.calls[0][0]).toBe("/v1/dashboard");
    expect(d.kycPending).toBe(3);
  });
});

describe("dashboard screen", () => {
  it("links an attention row to its line or to the customer's KYC, and shows no trends without data", async () => {
    realMode();
    fetchMock.mockImplementation(() => json(dashboard));
    wrap(<DashboardScreen />);
    const view = await screen.findByRole("link", { name: /^view$/i }, { timeout: 5000 });
    expect(view).toHaveAttribute("href", "/lines/7");
    expect(screen.getByRole("link", { name: /review kyc/i })).toHaveAttribute("href", "/customers?customer=2");
    expect(screen.getByText(/no line yet/i)).toBeInTheDocument();
    expect(screen.getByText(/no top-ups yesterday/i)).toBeInTheDocument(); // not a division by zero
    expect(screen.queryByText(/this week$/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: /^plan$/i })).not.toBeInTheDocument();
  });
});

describe("plans", () => {
  it("lists the plans on sale with their state", async () => {
    realMode();
    fetchMock.mockImplementation(() => json(planList));
    const plans = await getPlans();
    expect(fetchMock.mock.calls[0][0]).toBe("/v1/plans");
    expect(plans.map((p) => [p.planId, p.status])).toEqual([["1", "on_sale"], ["2", "retired"]]);
    expect(plans[0]).toMatchObject({ name: "Demo Weekly", priceKobo: 120000, channels: ["data"] });
  });

  it("is read-only against the real API: no create buttons, a plain note, and no bundle list", async () => {
    realMode();
    fetchMock.mockImplementation(() => json(planList));
    wrap(<PlansScreen />, "/plans?open=plan:1");
    expect(await screen.findByText("Demo Weekly", {}, { timeout: 5000 })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /create plan/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /create bundle/i })).not.toBeInTheDocument();
    expect(screen.getByText(/ops_cli/i)).toBeInTheDocument();
    expect(screen.getByText(/cannot list bundles yet/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/kyc|retire/i)).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.every(([url]) => url === "/v1/plans")).toBe(true); // nothing invented was called
  });

  it("can still create a plan on mock data", async () => {
    const user = userEvent.setup();
    wrap(<PlansScreen />);
    expect(await screen.findByRole("button", { name: /create plan/i }, { timeout: 5000 })).toBeEnabled();
    await user.click(screen.getByRole("button", { name: /create bundle/i }));
  });
});
