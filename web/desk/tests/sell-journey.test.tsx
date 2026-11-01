import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect } from "vitest";
import { mockNumbers, mockSims } from "../src/screens/sell-sim/mock";
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

    const resultButton = await waitFor(
      () => screen.getByRole("button", { name: /danjuma/i }),
      { timeout: 5000 }
    );
    await user.click(resultButton);

    const continueBtn = screen.getByRole("button", { name: /^continue$/i });
    expect(continueBtn).toBeDisabled();
  });

  it("lets a KYC-verified customer proceed", async () => {
    const user = userEvent.setup();
    renderSellSim();

    const search = screen.getByRole("textbox", { name: /search customers/i });
    await user.type(search, "fatima");

    const resultButton = await waitFor(
      () => screen.getByRole("button", { name: /fatima/i }),
      { timeout: 5000 }
    );
    await user.click(resultButton);

    const continueBtn = screen.getByRole("button", { name: /^continue$/i });
    expect(continueBtn).not.toBeDisabled();
  });

  it("sells a line end to end: create, the customer tops up, buy the plan, activate", async () => {
    const user = userEvent.setup();
    renderSellSim();

    await user.type(screen.getByRole("textbox", { name: /search customers/i }), "fatima");
    await user.click(await screen.findByRole("button", { name: /fatima/i }, { timeout: 5000 }));
    await user.click(screen.getByRole("button", { name: /^continue$/i }));

    await user.selectOptions(await screen.findByLabelText(/free sim/i), mockSims[0].iccid);
    await user.selectOptions(await screen.findByLabelText(/available number/i), mockNumbers[0]);
    await user.click(screen.getByRole("button", { name: /^continue$/i }));

    await user.click(await screen.findByRole("radio", { name: /weekly 2gb/i }));
    await user.click(screen.getByRole("button", { name: /continue to review/i }));
    await user.click(screen.getByRole("button", { name: /^create line$/i }));

    expect(await screen.findByRole("heading", { name: /collect payment and activate/i }, { timeout: 5000 })).toBeInTheDocument();
    // Nothing can be bought or activated before the customer has paid.
    expect(screen.getByRole("button", { name: /^buy plan$/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /^activate line$/i })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: /simulate a card top-up/i }));
    await waitFor(() => expect(screen.getByRole("button", { name: /^buy plan$/i })).toBeEnabled(), { timeout: 5000 });
    await user.click(screen.getByRole("button", { name: /^buy plan$/i }));
    await waitFor(() => expect(screen.getByRole("button", { name: /^activate line$/i })).toBeEnabled(), { timeout: 5000 });
    await user.click(screen.getByRole("button", { name: /^activate line$/i }));

    expect(await screen.findByRole("heading", { name: /line activated/i }, { timeout: 5000 })).toBeInTheDocument();
    expect(screen.getByText(/of which VAT/i)).toBeInTheDocument();
  });
});
