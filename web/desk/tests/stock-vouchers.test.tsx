// Stock & Vouchers against contract-shaped bodies (tests/fixtures/contract, checked against contracts/openapi.yaml by
// tests/contract/test_desk_fixtures.py): only the Vouchers tab, request, print (a one-time PDF), lookup.
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import StockScreen from "../src/screens/stock/StockScreen";
import { batchesFromWire, cardFromWire, type WireBatches, type WireCard } from "../src/screens/stock/contract";
import batches from "./fixtures/contract/VoucherBatches.demo.json";
import card from "./fixtures/contract/VoucherCard.demo.json";

const fetchMock = vi.fn();
const json = (body: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
const realMode = () => { vi.stubEnv("MODE", "development"); vi.stubEnv("VITE_USE_MOCK", "false"); vi.stubGlobal("fetch", fetchMock); };
beforeEach(() => fetchMock.mockReset());
afterEach(() => { vi.unstubAllEnvs(); vi.stubEnv("VITE_USE_MOCK", "true"); vi.unstubAllGlobals(); });

const wrap = () => {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}><MemoryRouter initialEntries={["/inventory"]}><StockScreen /></MemoryRouter></QueryClientProvider>);
};
const calls = (method: string, path: string) => fetchMock.mock.calls.filter(([url, init]) => String(url).endsWith(path) && (init?.method ?? "GET") === method);

describe("voucher mapping", () => {
  it("maps batches and a card, and a card never carries more than its last four digits", () => {
    const b = batchesFromWire(batches as WireBatches);
    expect(b.voucherValuesKobo).toEqual([10000, 20000, 50000, 100000, 200000]);
    expect(b.items[1]).toMatchObject({ batchId: 1, name: "V-00001", state: "on_sale", cardsUsed: 3, printedBy: "admin@ratelplus.net.ng" });
    const c = cardFromWire(card as WireCard);
    expect(c).toMatchObject({ voucherId: 7, last4: "4821", batch: "V-00001", usedByMsisdn: "2342064730433" });
    expect(Object.keys(c)).not.toContain("cardNumber");
  });
});

describe("the Vouchers tab on the real API", () => {
  it("shows only Vouchers, the batches, and the step each one is at", async () => {
    realMode();
    fetchMock.mockImplementation(() => json(batches));
    wrap();
    expect(await screen.findByText("V-00002")).toBeInTheDocument();
    expect(screen.getAllByRole("tab").map((t) => t.textContent)).toEqual(["Vouchers"]);
    const approved = screen.getByText("V-00002").closest("tr") as HTMLElement;
    expect(within(approved).getByRole("button", { name: "Print PDF" })).toBeInTheDocument();
    const onSale = screen.getByText("V-00001").closest("tr") as HTMLElement;
    expect(within(onSale).getByText("on sale")).toBeInTheDocument();
    expect(within(onSale).getByText("(3 used)")).toBeInTheDocument();
  });

  it("requests a batch with a face value from the catalogue's list, in kobo, with a key", async () => {
    realMode();
    const user = userEvent.setup();
    fetchMock.mockImplementation((url: string, init?: RequestInit) => (init?.method === "POST" ? json({ batch: batches.items[0], replayed: false }, 201) : json(batches)));
    wrap();
    await user.click(await screen.findByRole("button", { name: "Request voucher batch" }));
    await user.selectOptions(screen.getByLabelText("Face value"), "100000");
    await user.clear(screen.getByLabelText("Number of cards"));
    await user.type(screen.getByLabelText("Number of cards"), "48");
    await user.type(screen.getByLabelText(/what it is for/i), "Demo stock");
    await user.click(screen.getByRole("button", { name: "Request batch" }));
    await waitFor(() => expect(calls("POST", "/v1/voucher-batches")).toHaveLength(1));
    const [, init] = calls("POST", "/v1/voucher-batches")[0];
    expect(JSON.parse(init.body)).toEqual({ face_value_kobo: 100000, card_count: 48, reason: "Demo stock" });
    expect(init.headers["Idempotency-Key"]).toBeTruthy();
  });

  it("prints an approved batch once, as a PDF download", async () => {
    realMode();
    const user = userEvent.setup();
    const created = vi.fn(() => "blob:sheet");
    vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: created, revokeObjectURL: vi.fn() }));
    fetchMock.mockImplementation((url: string) =>
      String(url).endsWith("/print") ? Promise.resolve(new Response("%PDF-1.4", { status: 200, headers: { "Content-Type": "application/pdf" } })) : json(batches));
    wrap();
    const row = (await screen.findByText("V-00002")).closest("tr") as HTMLElement;
    await user.click(within(row).getByRole("button", { name: "Print PDF" }));
    expect(screen.getByText(/downloads them once, as a PDF/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Make cards and download PDF" }));
    await waitFor(() => expect(calls("POST", "/v1/voucher-batches/2/print")).toHaveLength(1));
    const [, init] = calls("POST", "/v1/voucher-batches/2/print")[0];
    expect(init.cache).toBe("no-store");
    await waitFor(() => expect(document.querySelector(".alert--danger")?.textContent ?? "").toBe(""));
    await waitFor(() => expect(created).toHaveBeenCalledTimes(1));
  });

  it("looks a card up by its number in the request body and shows the last four digits only", async () => {
    realMode();
    const user = userEvent.setup();
    fetchMock.mockImplementation((url: string) => (String(url).endsWith("/v1/vouchers/lookup") ? json(card) : json(batches)));
    wrap();
    await user.type(await screen.findByLabelText(/card number/i), "1234 5678 9012 3456 4821");
    await user.click(screen.getByRole("button", { name: "Look up" }));
    expect(await screen.findByText("•••• •••• •••• •••• 4821")).toBeInTheDocument();
    const [url, init] = calls("POST", "/v1/vouchers/lookup")[0];
    expect(String(url)).not.toContain("1234");
    expect(JSON.parse(init.body)).toEqual({ card_number: "12345678901234564821" });
    expect(screen.getByRole("button", { name: "Lock card" })).toBeDisabled(); // a used card cannot be locked
  });
});
