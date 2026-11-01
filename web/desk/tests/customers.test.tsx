import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect } from "vitest";
import { MemoryRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthContext, type AuthUser } from "../src/lib/authContext";
import CustomersScreen from "../src/screens/customers/CustomersScreen";

function renderCustomers(role: AuthUser["role"], entry = "/customers?kyc=pending") {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const auth = { user: { name: "Test Staff", email: "staff@example.test", role }, ready: true, signIn: async () => {}, signOut: async () => {} };
  return render(
    <AuthContext.Provider value={auth}>
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[entry]}>
          <CustomersScreen />
        </MemoryRouter>
      </QueryClientProvider>
    </AuthContext.Provider>,
  );
}

const openFirst = async (user: ReturnType<typeof userEvent.setup>) => {
  const names = await screen.findAllByRole("button", { name: /\w+ \w+/ }, { timeout: 5000 });
  await user.click(names.find((b) => b.className.includes("cust-name"))!);
};

describe("Customers (mock mode)", () => {
  it("has no NIN column in the list, as the API's list has none", async () => {
    renderCustomers("Super Admin");
    await screen.findAllByRole("row", {}, { timeout: 5000 });
    expect(screen.queryByRole("columnheader", { name: /nin/i })).not.toBeInTheDocument();
  });

  it("lets an admin approve a pending customer", async () => {
    const user = userEvent.setup();
    renderCustomers("Super Admin");
    await openFirst(user);
    const approve = await screen.findByRole("button", { name: /^approve$/i }, { timeout: 5000 });
    expect(screen.getByRole("button", { name: /^reject$/i })).toBeDisabled(); // a rejection needs a reason
    await user.click(approve);
    expect(await screen.findByText(/decision has already been recorded/i, {}, { timeout: 5000 })).toBeInTheDocument();
  });

  it("tells an agent that only an admin decides KYC, and offers no buttons", async () => {
    const user = userEvent.setup();
    renderCustomers("Customer Care");
    await openFirst(user);
    expect(await screen.findByText(/only an admin decides kyc/i, {}, { timeout: 5000 })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^approve$/i })).not.toBeInTheDocument();
  });
});
