import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthContext, type AuthUser } from "../src/lib/authContext";
import LineDetailScreen from "../src/screens/line-detail/LineDetailScreen";

// Mock lines are numbered from 100. 100 is active, 128 awaits activation. Each care test uses its own line.
const ACTIVE = "100";
const AWAITING = "128";

function renderLineDetail(lineId = ACTIVE, role: AuthUser["role"] = "Super Admin") {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const auth = { user: { name: "Test Staff", email: "staff@example.test", role }, ready: true, signIn: async () => {}, signOut: async () => {} };
  return render(
    <AuthContext.Provider value={auth}>
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[`/lines/${lineId}`]}>
          <Routes>
            <Route path="/lines/:lineId" element={<LineDetailScreen />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </AuthContext.Provider>,
  );
}

const findButton = (name: RegExp) => screen.findByRole("button", { name }, { timeout: 5000 });

describe("Line detail page (mock mode)", () => {
  it("shows the four tabs and the attach notice", async () => {
    renderLineDetail();
    expect(await screen.findByText(/Changes take effect when the phone next attaches/i, {}, { timeout: 5000 })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /overview/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /usage/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /calls/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /history/i })).toBeInTheDocument();
  });

  it("switches to the Usage tab and shows intervals", async () => {
    const user = userEvent.setup();
    renderLineDetail();
    await user.click(await screen.findByRole("tab", { name: /usage/i }, { timeout: 5000 }));
    expect(await screen.findByText(/Usage: 5-minute intervals/i, {}, { timeout: 5000 })).toBeInTheDocument();
  });

  it("switches to the Calls tab and shows how each call ended, without a bearer column", async () => {
    const user = userEvent.setup();
    renderLineDetail();
    await user.click(await screen.findByRole("tab", { name: /calls/i }, { timeout: 5000 }));
    expect((await screen.findAllByText("Answered", {}, { timeout: 5000 })).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/could not be reached/i).length).toBeGreaterThan(0);
    expect(screen.queryByText(/QCI/i)).not.toBeInTheDocument();
    expect(screen.getByText(/from the last 30 days/i)).toBeInTheDocument();
  }, 15000);

  it("is still reachable by IMSI for the screens that link that way", async () => {
    renderLineDetail("621000000000100");
    expect(await screen.findByRole("heading", { name: /234 700 000 0100/ }, { timeout: 5000 })).toBeInTheDocument();
  });

  it("suspends a line with a reason, then reinstates it", async () => {
    const user = userEvent.setup();
    renderLineDetail("101");
    await user.click(await findButton(/^suspend line$/i));
    expect(await screen.findByRole("heading", { name: /suspend .*\?/i })).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText(/^reason$/i), "lost_sim");
    await user.type(screen.getByLabelText(/additional note/i), "phone stolen");
    await user.click(screen.getAllByRole("button", { name: /^suspend line$/i }).at(-1)!);

    // It is suspended now: reinstating is offered, suspending is not.
    await user.click(await findButton(/^reinstate line$/i));
    expect(screen.queryByRole("button", { name: /^suspend line$/i })).not.toBeInTheDocument();
    await user.click(screen.getAllByRole("button", { name: /^reinstate line$/i }).at(-1)!);
    expect(await findButton(/^suspend line$/i)).toBeEnabled();
  });

  it("lets only an admin terminate, and terminating is final", async () => {
    const user = userEvent.setup();
    const { unmount } = renderLineDetail("102", "Customer Care");
    await findButton(/^suspend line$/i);
    expect(screen.queryByRole("button", { name: /terminate line/i })).not.toBeInTheDocument();
    unmount();

    renderLineDetail("102", "Super Admin");
    await user.click(await findButton(/^terminate line$/i));
    expect(await screen.findByText(/this is final/i)).toBeInTheDocument();
    await user.click(screen.getAllByRole("button", { name: /^terminate line$/i }).at(-1)!);
    await waitFor(() => expect(screen.queryByRole("button", { name: /^terminate line$/i })).not.toBeInTheDocument(), { timeout: 5000 });
    expect(screen.getByRole("button", { name: /^suspend line$/i })).toBeDisabled();
  });

  it("picks up a sale that stopped before activation", async () => {
    const user = userEvent.setup();
    renderLineDetail(AWAITING);
    expect(await screen.findByRole("heading", { name: /collect payment and activate/i }, { timeout: 5000 })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^buy plan$/i })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: /simulate a card top-up/i }));
    await waitFor(() => expect(screen.getByRole("button", { name: /^buy plan$/i })).toBeEnabled(), { timeout: 5000 });
    await user.click(screen.getByRole("button", { name: /^buy plan$/i }));
    await waitFor(() => expect(screen.getByRole("button", { name: /^activate line$/i })).toBeEnabled(), { timeout: 5000 });
    await user.click(screen.getByRole("button", { name: /^activate line$/i }));
    expect(await screen.findByRole("heading", { name: /line activated/i }, { timeout: 5000 })).toBeInTheDocument();
  });
});
