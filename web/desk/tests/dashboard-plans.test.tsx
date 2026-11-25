// The dashboard and plans screens against contract-shaped bodies (tests/fixtures/contract, checked against
// contracts/openapi.yaml by tests/contract/test_desk_fixtures.py).
import { render, screen, waitFor } from "@testing-library/react";
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
import catalogue from "./fixtures/contract/Catalogue.demo.json";
import auditPage from "./fixtures/contract/CatalogueAuditPage.demo.json";
import { historyFromWire, type WireAuditPage } from "../src/screens/plans/contract";

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
  const created = () => Promise.resolve(new Response(JSON.stringify({ offer_id: 5, replayed: false }), { status: 201, headers: { "Content-Type": "application/json" } }));

  it("lists plans and bundles, on sale and retired, from the catalogue", async () => {
    realMode();
    fetchMock.mockImplementation(() => json(catalogue));
    const plans = await getPlans();
    expect(fetchMock.mock.calls[0][0]).toBe("/v1/catalogue");
    expect(plans).toEqual([expect.objectContaining({ planId: "1", name: "Home 10 Mbps", onExhaustion: "slow", slowDlMbps: 2, channels: ["desk"], status: "on_sale" })]);
    wrap(<PlansScreen />);
    expect(await screen.findByText("Weekly 3GB", {}, { timeout: 5000 })).toBeInTheDocument();
    expect(screen.getByText("Old 1GB")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /create bundle/i })).toBeEnabled();
    expect(await screen.findByLabelText(/smallest top-up/i)).toHaveValue("20");
    expect(screen.getByLabelText(/calls to other networks/i)).toHaveValue("20");
  });

  it("publishes a bundle with the reason, the channels and an Idempotency-Key", async () => {
    realMode();
    const user = userEvent.setup();
    fetchMock.mockImplementation((_url: string, init?: RequestInit) => (init?.method === "POST" ? created() : json(catalogue)));
    wrap(<PlansScreen />, "/plans?open=new:bundle");
    await user.type(await screen.findByLabelText("Name", {}, { timeout: 5000 }), "Daily 500MB");
    await user.type(screen.getByLabelText(/price/i), "100");
    await user.type(screen.getByLabelText(/validity/i), "1");
    await user.type(screen.getByLabelText(/data \(gb\)/i), "0.5");
    expect(screen.getByText(/₦200 per GB/)).toBeInTheDocument();
    await user.click(screen.getByLabelText("RatelPay page")); // off: desk, sms and ussd stay on
    const submit = () => screen.getAllByRole("button", { name: /^create bundle$/i }).at(-1) as HTMLElement; // the drawer's, not the page's
    await user.click(submit());
    expect(screen.getByText(/say why/i)).toBeInTheDocument(); // no reason, nothing sent
    await user.type(screen.getByLabelText(/reason for this change/i), "November price list");
    await user.click(submit());
    await waitFor(() => expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(true));
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
    expect(post?.[0]).toBe("/v1/catalogue/offers");
    expect(JSON.parse(post?.[1].body)).toEqual({
      kind: "bundle", name: "Daily 500MB", price_kobo: 10000, data_bytes: 500000000, validity_days: 1, channels: ["desk", "sms", "ussd"], reason: "November price list",
    });
    expect(post?.[1].headers["Idempotency-Key"]).toBeTruthy();
  });

  it("reads an offer's history from the catalogue audit trail", () => {
    const history = historyFromWire(auditPage as WireAuditPage, "bundle", "2");
    expect(history.map((h) => h.action)).toEqual(["Bundle published", "Bundle retired"]);
    expect(history[1]).toMatchObject({ actor: "admin@example.test", detail: "November price list | was on_sale" });
  });

  it("can still create a plan on mock data", async () => {
    const user = userEvent.setup();
    wrap(<PlansScreen />);
    expect(await screen.findByRole("button", { name: /create plan/i }, { timeout: 5000 })).toBeEnabled();
    await user.click(screen.getByRole("button", { name: /create bundle/i }));
  });
});
