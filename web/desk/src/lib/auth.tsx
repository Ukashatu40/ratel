import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { ApiError, apiGet, apiPost, setUnauthorizedHandler } from "./api";
import { AuthContext, type AuthUser, type AuthValue } from "./authContext";

// What POST /v1/auth/login and GET /v1/auth/me answer (StaffMe in the contract).
interface StaffMe { staff_id: number; email: string; name: string; role: string }

// The API's roles (PRODUCT_RULES.md) under the names the screens show. An unknown role gets the lower one.
const ROLE_LABEL: Record<string, AuthUser["role"]> = { agent: "Customer Care", admin: "Super Admin" };
const toUser = (me: StaffMe): AuthUser => ({ name: me.name, email: me.email, role: ROLE_LABEL[me.role] ?? "Customer Care" });

// With VITE_USE_MOCK=true there is no backend to ask, so sign-in is a stand-in that remembers the user for the tab.
const isMock = () => import.meta.env.VITE_USE_MOCK === "true";
const MOCK_KEY = "ratel.desk.mock-user";

// MOCK rule until the backend says who is who: emails starting with "admin" (and ibrahim.danladi) are Super Admins.
// (PRD decision 11 uses the API names "agent"/"admin"; the UI shows the friendly pair.)
const roleFromEmail = (email: string): AuthUser["role"] => {
  const local = email.split("@")[0].toLowerCase();
  return local.startsWith("admin") || local === "ibrahim.danladi" ? "Super Admin" : "Customer Care";
};

// "amina.yusuf@ratelplus.example" -> "Amina Yusuf"
const nameFromEmail = (email: string) =>
  email.split("@")[0].split(/[._-]/).filter(Boolean).map((w) => w[0].toUpperCase() + w.slice(1)).join(" ");

function loadMock(): AuthUser | null {
  try {
    const raw = sessionStorage.getItem(MOCK_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as AuthUser;
    // Old sessionStorage entries may carry the API role names; convert them to the labels the UI uses.
    if ((parsed.role as string) === "admin") return { ...parsed, role: "Super Admin" };
    if ((parsed.role as string) === "agent") return { ...parsed, role: "Customer Care" };
    return parsed;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const mock = isMock();
  const [user, setUser] = useState<AuthUser | null>(mock ? loadMock : null);
  const [ready, setReady] = useState(mock);

  // The cookie outlives a page reload, so ask the API who we are before deciding what to show.
  useEffect(() => {
    if (mock) return;
    let cancelled = false;
    apiGet<StaffMe>("/v1/auth/me")
      .then((me) => !cancelled && setUser(toUser(me)))
      .catch(() => undefined) // 401 (no session) or the API is down: show the sign-in page
      .finally(() => !cancelled && setReady(true));
    return () => {
      cancelled = true;
    };
  }, [mock]);

  // A 401 on any later call means the session ended: go back to sign-in.
  useEffect(() => {
    if (mock) return;
    setUnauthorizedHandler(() => setUser(null));
    return () => setUnauthorizedHandler(null);
  }, [mock]);

  const signIn = useCallback(
    async (email: string, password: string) => {
      if (mock) {
        const u: AuthUser = { email, name: nameFromEmail(email) || "Staff", role: roleFromEmail(email) };
        sessionStorage.setItem(MOCK_KEY, JSON.stringify(u));
        setUser(u);
        return;
      }
      setUser(toUser(await apiPost<StaffMe>("/v1/auth/login", { email, password })));
    },
    [mock],
  );

  const signOut = useCallback(async () => {
    if (mock) sessionStorage.removeItem(MOCK_KEY);
    else await apiPost("/v1/auth/logout", {}).catch((e: unknown) => { if (!(e instanceof ApiError)) throw e; }); // the API always answers 204; a refusal changes nothing here
    setUser(null);
  }, [mock]);

  const value = useMemo<AuthValue>(() => ({ user, ready, signIn, signOut }), [user, ready, signIn, signOut]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}