import { useMemo, useState, type ReactNode } from "react";
import { AuthContext, type AuthUser, type AuthValue } from "./authContext";

// MOCK-PHASE sign-in: remembers the user in sessionStorage. Replace signIn/signOut with real calls to the backend later.
const KEY = "ratel.desk.user";

// "amina.yusuf@ratelplus.example" -> "Amina Yusuf"
const nameFromEmail = (email: string) =>
  email.split("@")[0].split(/[._-]/).filter(Boolean).map((w) => w[0].toUpperCase() + w.slice(1)).join(" ");

// MOCK rule until the backend says who is who: emails starting with "admin" (and ibrahim.danladi) are admins (PRD decision 11).
const roleFromEmail = (email: string): AuthUser["role"] => {
  const local = email.split("@")[0].toLowerCase();
  return local.startsWith("admin") || local === "ibrahim.danladi" ? "admin" : "agent";
};

function load(): AuthUser | null {
  try {
    const raw = sessionStorage.getItem(KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as AuthUser;
    // Old sessionStorage entries may have the previous role names; normalise them.
    if ((parsed.role as string) === "Super Admin") return { ...parsed, role: "admin" };
    if ((parsed.role as string) === "Customer Care") return { ...parsed, role: "agent" };
    return parsed;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(load);
  const value = useMemo<AuthValue>(
    () => ({
      user,
      signIn: (email) => {
        const u: AuthUser = { email, name: nameFromEmail(email) || "Staff", role: roleFromEmail(email) }; // role will come from the backend
        sessionStorage.setItem(KEY, JSON.stringify(u));
        setUser(u);
      },
      signOut: () => {
        sessionStorage.removeItem(KEY);
        setUser(null);
      },
    }),
    [user],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
