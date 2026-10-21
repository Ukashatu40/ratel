import { useAuth, type AuthUser } from "./authContext";

// The signed-in staff member. Only used on screens that sit behind <RequireAuth>.
export const useCurrentUser = (): AuthUser => useAuth().user ?? { name: "Staff", email: "", role: "Customer Care" };