import { createContext, useContext } from "react";

// The role names shown in the UI. The API uses "agent" / "admin" (PRODUCT_RULES.md, decision 11);
// this file only concerns the labels the screens use, so keep the friendly pairs here.
export interface AuthUser { name: string; email: string; role: "Customer Care" | "Super Admin" }
export interface AuthValue {
  user: AuthUser | null;
  ready: boolean; // false until we know whether a session exists (the page just loaded)
  signIn: (email: string, password: string) => Promise<void>; // throws ApiError when refused
  signOut: () => Promise<void>;
}

export const AuthContext = createContext<AuthValue | null>(null);

export function useAuth(): AuthValue {
  const v = useContext(AuthContext);
  if (!v) throw new Error("useAuth must be used inside <AuthProvider>");
  return v;
}