// The wallet and ledger against contract-shaped bodies (tests/fixtures/contract, checked against
// contracts/openapi.yaml by tests/contract/test_desk_fixtures.py), and the screen in both modes.
import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import customer from "./fixtures/contract/Customer.created.json";
import ledger from "./fixtures/contract/LedgerPage.json";
import lineActive from "./fixtures/contract/Line.active.json";
import lineWallet from "./fixtures/contract/LineWallet.json";
import summary from "./fixtures/contract/WalletSummary.json";
import * as real from "../src/screens/wallet/realApi";
import WalletScreen from "../src/screens/wallet/WalletScreen";

const fetchMock = vi.fn();
const json = (body: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
const realMode = () => { vi.stubEnv("MODE", "development"); vi.stubEnv("VITE_USE_MOCK", "false"); vi.stubGlobal("fetch", fetchMock); };
beforeEach(() => fetchMock.mockReset());
afterEach(() => { vi.unstubAllEnvs(); vi.stubEnv("VITE_USE_MOCK", "true"); vi.unstubAllGlobals(); });
const urls = () => fetchMock.mock.calls.map(([u]) => new URL(u as string, "http://x"));

const route = (bodies: Record<string, unknown>) =>
  fetchMock.mockImplementation((url: string) => {
    const path = new URL(url, "http://x").pathname;
    return path in bodies ? json(bodies[path]) : json({ error: { code: "not_found", message: "x" } }, 404);
  });

const renderWallet = (entry = "/finance/wallet") => {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}><MemoryRouter initialEntries={[entry]}><WalletScreen /></MemoryRouter></QueryClientProvider>);
};

describe("the real calls", () => {
  it("asks for a page of the ledger, by kind and by line id", async () => {
    realMode();
    route({ "/v1/ledger": ledger });
    const page = await real.getLedger({ kind: "top_up", line: "7", page: 2, pageSize: 10 });
    expect(Object.fromEntries(urls()[0].searchParams)).toEqual({ page: "2", page_size: "10", kind: "top_up", line_id: "7" });
    expect(page.total).toBe(3);
    expect(page.counts).toEqual({ all: 3, top_up: 1, purchase: 1, vat: 1 });
    expect(page.items[0]).toEqual({ entryId: 12, lineId: 7, msisdn: "2347000000150", amountKobo: -8372, kind: "vat", reference: "PUR-7-1", createdAt: 1794690100 });
  });

  it("leaves the kind and the line out for the whole ledger", async () => {
    realMode();
    route({ "/v1/ledger": ledger });
    await real.getLedger({ kind: "all", line: null, page: 1, pageSize: 10 });
    expect(Object.fromEntries(urls()[0].searchParams)).toEqual({ page: "1", page_size: "10" });
  });

  it("maps the summary, which has no trend because RatelBSS keeps no balance history", async () => {
    realMode();
    route({ "/v1/wallet/summary": summary });
    const s = await real.getWalletSummary();
    expect(s).toMatchObject({ totalBalanceKobo: 30000, walletsWithBalance: 1, entriesToday: 3, trends: null });
    expect(s.daily.at(-1)).toEqual({ date: "2026-11-01", inKobo: 150000, outKobo: 120000 });
  });

  it("puts a line's wallet together from the wallet, the line and its customer's name", async () => {
    realMode();
    route({ "/v1/lines/7": lineActive, "/v1/lines/7/wallet": lineWallet, "/v1/customers/1": customer });
    const w = await real.getLineWallet("7");
    expect(w).toEqual({ lineId: 7, msisdn: "2347000000150", customerName: "Demo Customer Three", balanceKobo: 150000, ledgerSumKobo: 150000 });
  });

  it("refuses a line key that is not a whole number before asking the API", async () => {
    realMode();
    await expect(real.getLineWallet("621000000000150x")).rejects.toThrow(/valid id/);
    await expect(real.getLedger({ kind: "all", line: "abc", page: 1, pageSize: 10 })).rejects.toThrow(/valid id/);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("the screen against the real API", () => {
  it("shows the API's kinds as tabs, links each entry to its line, and draws no trends", async () => {
    realMode();
    route({ "/v1/ledger": ledger, "/v1/wallet/summary": summary });
    renderWallet();
    const link = (await screen.findAllByRole("link", { name: /\+234 700 000 0150/ }, { timeout: 5000 }))[0];
    expect(link).toHaveAttribute("href", "/lines/7");
    const tabs = screen.getAllByRole("tab").map((t) => t.textContent);
    expect(tabs).toEqual(["All (3)", "Top-ups (1)", "Plan purchases (1)", "VAT (1)", "Corrections (0)"]);
    expect(screen.queryByText(/this week/i)).not.toBeInTheDocument();
  });

  it("shows a line's wallet and whether it matches the ledger", async () => {
    realMode();
    route({ "/v1/ledger": ledger, "/v1/wallet/summary": summary, "/v1/lines/7": lineActive, "/v1/lines/7/wallet": lineWallet, "/v1/customers/1": customer });
    renderWallet("/finance/wallet?line=7");
    expect(await screen.findByText(/matches the ledger/i, {}, { timeout: 5000 })).toBeInTheDocument();
    expect(Object.fromEntries(urls().find((u) => u.pathname === "/v1/ledger")!.searchParams).line_id).toBe("7");
  });

  it("says plainly when the wallet and the ledger disagree", async () => {
    realMode();
    route({ "/v1/ledger": ledger, "/v1/wallet/summary": summary, "/v1/lines/7": lineActive, "/v1/lines/7/wallet": { ...lineWallet, ledger_sum_kobo: 149000 }, "/v1/customers/1": customer });
    renderWallet("/finance/wallet?line=7");
    expect(await screen.findByText(/does not match the ledger/i, {}, { timeout: 5000 })).toBeInTheDocument();
  });
});

describe("the screen on mock data", () => {
  it("lists the API's kinds and a wallet that matches its ledger", async () => {
    renderWallet("/finance/wallet?line=100");
    expect(await screen.findByText(/matches the ledger/i, {}, { timeout: 5000 })).toBeInTheDocument();
    expect(screen.getAllByRole("tab").map((t) => t.textContent?.replace(/\s*\(\d+\)$/, ""))).toEqual(["All", "Top-ups", "Plan purchases", "VAT", "Corrections"]);
  });
});
