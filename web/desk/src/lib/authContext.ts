import { createContext, useContext } from "react";

// Roles: "agent" and "admin" (PRD decision 11, demo only). Reviewed before pilot.
export interface AuthUser { name: string; email: string; role: "agent" | "admin" }
export interface AuthValue { user: AuthUser | null; signIn: (email: string) => void; signOut: () => void }

export const AuthContext = createContext<AuthValue | null>(null);

export function useAuth(): AuthValue {
  const v = useContext(AuthContext);
  if (!v) throw new Error("useAuth must be used inside <AuthProvider>");
  return v;
}
