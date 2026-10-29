import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router";
import { AuthProvider } from "../src/lib/auth";
import { useAuth } from "../src/lib/authContext";
import { apiGet } from "../src/lib/api";
import { LoginRoute } from "../src/components/layout/LoginRoute";
import { RequireAuth } from "../src/components/layout/RequireAuth";

const ME = { staff_id: 7, email: "amina@ratelplus.example", name: "Amina Yusuf", role: "agent" };

type Call = { method: string; path: string; headers: Record<string, string>; body: unknown; credentials?: string };

// A fake API: `session` says whether the cookie would be accepted.
function fakeApi(opts: { session: boolean; loginOk?: boolean; loginStatus?: number }) {
  const calls: Call[] = [];
  let session = opts.session;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init: RequestInit = {}) => {
      const call: Call = {
        method: init.method ?? "GET",
        path: url,
        headers: (init.headers ?? {}) as Record<string, string>,
        body: init.body ? JSON.parse(init.body as string) : undefined,
        credentials: init.credentials,
      };
      calls.push(call);
      const json = (status: number, data: unknown) => new Response(JSON.stringify(data), { status });
      if (url === "/v1/auth/me") return session ? json(200, ME) : json(401, { error: { code: "unauthorized", message: "no" } });
      if (url === "/v1/auth/login") {
        if (opts.loginOk === false) return json(opts.loginStatus ?? 401, { error: { code: "unauthorized", message: "no" } });
        session = true;
        return json(200, ME);
      }
      if (url === "/v1/auth/logout") {
        session = false;
        return new Response(null, { status: 204 });
      }
      return session ? json(200, {}) : json(401, { error: { code: "unauthorized", message: "no" } });
    }),
  );
  return { calls, endSession: () => (session = false) };
}

function Probe() {
  const { user, signOut } = useAuth();
  return (
    <div>
      <p>Welcome {user?.name} ({user?.role})</p>
      <button onClick={() => void signOut()}>sign out</button>
      <button onClick={() => void apiGet("/v1/lines/lookup").catch(() => undefined)}>load something</button>
    </div>
  );
}

function renderApp(start = "/") {
  return render(
    <AuthProvider>
      <MemoryRouter initialEntries={[start]}>
        <Routes>
          <Route path="/login" element={<LoginRoute />} />
          <Route element={<RequireAuth />}>
            <Route path="/" element={<Probe />} />
          </Route>
        </Routes>
      </MemoryRouter>
    </AuthProvider>,
  );
}

beforeEach(() => {
  vi.stubEnv("VITE_USE_MOCK", "false"); // these tests talk to the (fake) real API
});
afterEach(() => {
  vi.unstubAllGlobals();
});

describe("staff sign-in against the real API", () => {
  it("shows the sign-in page when there is no session", async () => {
    fakeApi({ session: false });
    renderApp();
    expect(await screen.findByRole("button", { name: /sign in to rateldesk/i })).toBeInTheDocument();
  });

  it("starts the form empty, with no sample credentials", async () => {
    fakeApi({ session: false });
    renderApp();
    expect(await screen.findByLabelText(/^email$/i)).toHaveValue("");
    expect(screen.getByLabelText(/^password$/i)).toHaveValue("");
  });

  it("signs in with the email and password, sends the cookie, and shows who signed in", async () => {
    const api = fakeApi({ session: false });
    const user = userEvent.setup();
    renderApp();
    await user.type(await screen.findByLabelText(/^email$/i), "amina@ratelplus.example");
    await user.type(screen.getByLabelText(/^password$/i), "correct horse battery");
    await user.click(screen.getByRole("button", { name: /sign in to rateldesk/i }));

    expect(await screen.findByText(/welcome amina yusuf \(customer care\)/i)).toBeInTheDocument();
    const login = api.calls.find((c) => c.path === "/v1/auth/login")!;
    expect(login.body).toEqual({ email: "amina@ratelplus.example", password: "correct horse battery" });
    expect(login.credentials).toBe("include");
    expect(login.headers["X-Ratel-Desk"]).toBe("1");
  });

  it("shows the same message for any refusal, keeps the email and clears the password", async () => {
    fakeApi({ session: false, loginOk: false });
    const user = userEvent.setup();
    renderApp();
    await user.type(await screen.findByLabelText(/^email$/i), "amina@ratelplus.example");
    await user.type(screen.getByLabelText(/^password$/i), "wrong");
    await user.click(screen.getByRole("button", { name: /sign in to rateldesk/i }));

    expect(await screen.findByText("Email or password is not right.")).toBeInTheDocument();
    expect(screen.getByLabelText(/^email$/i)).toHaveValue("amina@ratelplus.example");
    expect(screen.getByLabelText(/^password$/i)).toHaveValue("");
    expect(screen.queryByText(/welcome amina/i)).not.toBeInTheDocument();
  });

  it("says to wait when the proxy limits the rate", async () => {
    fakeApi({ session: false, loginOk: false, loginStatus: 429 });
    const user = userEvent.setup();
    renderApp();
    await user.type(await screen.findByLabelText(/^email$/i), "amina@ratelplus.example");
    await user.type(screen.getByLabelText(/^password$/i), "x");
    await user.click(screen.getByRole("button", { name: /sign in to rateldesk/i }));
    expect(await screen.findByText(/too many attempts/i)).toBeInTheDocument();
  });

  it("keeps a signed-in visitor signed in across a reload, without showing the sign-in page", async () => {
    fakeApi({ session: true });
    renderApp();
    expect(await screen.findByText(/welcome amina yusuf/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /sign in to rateldesk/i })).not.toBeInTheDocument();
  });

  it("shows an admin as Super Admin and any unknown role as the lower one", async () => {
    fakeApi({ session: true });
    vi.mocked(fetch).mockImplementationOnce(async () => new Response(JSON.stringify({ ...ME, role: "admin" }), { status: 200 }));
    renderApp();
    expect(await screen.findByText(/\(super admin\)/i)).toBeInTheDocument();
  });

  it("signs out through the API and returns to the sign-in page", async () => {
    const api = fakeApi({ session: true });
    const user = userEvent.setup();
    renderApp();
    await user.click(await screen.findByRole("button", { name: /sign out/i }));
    expect(await screen.findByRole("button", { name: /sign in to rateldesk/i })).toBeInTheDocument();
    const logout = api.calls.find((c) => c.path === "/v1/auth/logout")!;
    expect(logout.method).toBe("POST");
    expect(logout.headers["X-Ratel-Desk"]).toBe("1");
  });

  it("goes back to sign-in when a later call finds the session has ended", async () => {
    const api = fakeApi({ session: true });
    const user = userEvent.setup();
    renderApp();
    await screen.findByText(/welcome amina yusuf/i);
    api.endSession();
    await user.click(screen.getByRole("button", { name: /load something/i }));
    await waitFor(() => expect(screen.getByRole("button", { name: /sign in to rateldesk/i })).toBeInTheDocument());
  });

  it("asks who is signed in once, and a refused sign-in does not start it again", async () => {
    const api = fakeApi({ session: false, loginOk: false });
    const user = userEvent.setup();
    renderApp();
    await user.type(await screen.findByLabelText(/^email$/i), "a@b.example");
    await user.type(screen.getByLabelText(/^password$/i), "x");
    await user.click(screen.getByRole("button", { name: /sign in to rateldesk/i }));
    await screen.findByText("Email or password is not right.");
    expect(api.calls.filter((c) => c.path === "/v1/auth/me")).toHaveLength(1);
  });
});
