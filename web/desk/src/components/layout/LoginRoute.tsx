import { Navigate, useLocation } from "react-router";
import { useAuth } from "../../lib/authContext";
import { SignInScreen } from "../../screens/SignInScreen";

// Connects the sign-in screen to the router: after sign-in, go where the visitor wanted, or to the dashboard.
export function LoginRoute() {
  const { user, ready, signIn } = useAuth();
  const from = (useLocation().state as { from?: string } | null)?.from ?? "/";
  if (!ready) return null;
  if (user) return <Navigate to={from} replace />; // already signed in (or just signed in): go on
  return <SignInScreen onSignIn={signIn} />;
}
