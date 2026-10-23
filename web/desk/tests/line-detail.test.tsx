import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import LineDetailScreen from "../src/screens/line-detail/LineDetailScreen";

// The mock generates IMSIs as `621000000000${n}` with n starting at 100.
// TODO: switch to a real fixture when M-02 (RatelBSS) lands.
const MOCK_IMSI = "621000000000100";

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
      await screen.findByText(/Changes take effect when the phone next attaches/i)
    ).toBeInTheDocument();
    // Tabs have role="tab", not role="button"
    expect(screen.getByRole("tab", { name: /overview/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /usage/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /calls/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /history/i })).toBeInTheDocument();
  });

  it("switches to the Usage tab and shows intervals", async () => {
    const user = userEvent.setup();
    renderLineDetail();
    const usageTab = await screen.findByRole("tab", { name: /usage/i });
    await user.click(usageTab);
    expect(await screen.findByText(/Usage: 5-minute intervals/i)).toBeInTheDocument();
  });
});
