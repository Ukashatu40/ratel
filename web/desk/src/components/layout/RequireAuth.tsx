import { Navigate, Outlet, useLocation } from "react-router";
import { useAuth } from "../../lib/authContext";

// Sends signed-out visitors to /login, remembering where they wanted to go.
export function RequireAuth() {
  const { user } = useAuth();
  const location = useLocation();
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  return <Outlet />;
}