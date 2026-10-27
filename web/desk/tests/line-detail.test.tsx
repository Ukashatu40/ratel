import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import LineDetailScreen from "../src/screens/line-detail/LineDetailScreen";

const MOCK_IMSI = "621000000000100";

console.log("=== DIAGNOSTIC ===");
console.log("MODE:", import.meta.env.MODE);
console.log("VITE_USE_MOCK:", import.meta.env.VITE_USE_MOCK);
console.log("NODE:", typeof process !== "undefined" ? process.version : "no process");
console.log("=== END DIAGNOSTIC ===");

function renderLineDetail(imsi = MOCK_IMSI) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/lines/${imsi}`]}>
        <Routes>
          <Route path="/lines/:imsi" element={<LineDetailScreen />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("Line detail page (mock mode)", () => {
  it("shows the four tabs and the attach notice", async () => {
    renderLineDetail();
    expect(
      await screen.findByText(
        /Changes take effect when the phone next attaches/i,
        {},
        { timeout: 5000 }
      )
    ).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /overview/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /usage/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /calls/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /history/i })).toBeInTheDocument();
  });

  it("switches to the Usage tab and shows intervals", async () => {
    const user = userEvent.setup();
    renderLineDetail();
    const usageTab = await screen.findByRole(
      "tab",
      { name: /usage/i },
      { timeout: 5000 }
    );
    await user.click(usageTab);
    expect(
      await screen.findByText(
        /Usage: 5-minute intervals/i,
        {},
        { timeout: 5000 }
      )
    ).toBeInTheDocument();
  });
});