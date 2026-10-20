import { createContext, useContext } from "react";

export interface AuthUser { name: string; email: string; role: "Customer Care" | "Super Admin" }
export interface AuthValue { user: AuthUser | null; signIn: (email: string) => void; signOut: () => void }

export const AuthContext = createContext<AuthValue | null>(null);

export function useAuth(): AuthValue {
  const v = useContext(AuthContext);
  if (!v) throw new Error("useAuth must be used inside <AuthProvider>");
  return v;
}