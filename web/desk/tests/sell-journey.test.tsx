import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect } from "vitest";
import { MemoryRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import SellSimScreen from "../src/screens/sell-sim/SellSimScreen";

function renderSellSim() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <SellSimScreen />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("Sell SIM journey (mock mode)", () => {
  it("blocks a blocked customer from continuing to review", async () => {
    const user = userEvent.setup();
    renderSellSim();
    const search = screen.getByRole("textbox", { name: /search customers/i });
    await user.type(search, "danjuma");
    const resultButton = await screen.findByRole("button", { name: /danjuma/i });
    await user.click(resultButton);
    const continueBtn = screen.getByRole("button", { name: /^continue$/i });
    expect(continueBtn).toBeDisabled();
  });

  it("lets a KYC-verified customer proceed", async () => {
    const user = userEvent.setup();
    renderSellSim();
    const search = screen.getByRole("textbox", { name: /search customers/i });
    await user.type(search, "fatima");
    const resultButton = await screen.findByRole("button", { name: /fatima/i });
    await user.click(resultButton);
    const continueBtn = screen.getByRole("button", { name: /^continue$/i });
    expect(continueBtn).not.toBeDisabled();
  });
});