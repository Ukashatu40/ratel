import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect } from "vitest";
import { MemoryRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import LinesScreen from "../src/screens/lines/LinesScreen";

function renderLines(entry = "/lines") {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[entry]}>
        <LinesScreen />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Lines list (mock mode)", () => {
  it("has a tab for every state, so a line awaiting activation can be found", async () => {
    renderLines();
    await screen.findByRole("link", { name: /\+234 700 000 0100/ }, { timeout: 5000 });
    const tabs = screen.getAllByRole("tab").map((t) => t.textContent?.replace(/\s*\(\d+\)$/, ""));
    expect(tabs).toEqual(["All", "Awaiting activation", "Active", "Out of Data", "Suspended", "Expired", "Terminated"]);
  });

  it("links each line by its id and shows the number the way people read it", async () => {
    renderLines();
    const link = await screen.findByRole("link", { name: /\+234 700 000 0100/ }, { timeout: 5000 });
    expect(link).toHaveAttribute("href", "/lines/100");
  });

  it("offers Reinstate, not Suspend, for a suspended line", async () => {
    const user = userEvent.setup();
    renderLines("/lines?state=suspended");
    await user.click((await screen.findAllByRole("button", { name: /actions/i }, { timeout: 5000 }))[0]);
    expect(screen.getByRole("menuitem", { name: /reinstate/i })).toBeEnabled();
    expect(screen.queryByRole("menuitem", { name: /^suspend$/i })).not.toBeInTheDocument();
  });
});
