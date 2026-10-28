import { RouterProvider, createBrowserRouter } from "react-router";
import { AppShell } from "./components/layout/AppShell";
import { RequireAuth } from "./components/layout/RequireAuth";
import { LoginRoute } from "./components/layout/LoginRoute";
import DashboardScreen from "./screens/dashboard/DashboardScreen";
import CustomersScreen from "./screens/customers/CustomersScreen";
import LineDetailScreen from "./screens/line-detail/LineDetailScreen";
import LinesScreen from "./screens/lines/LinesScreen";
import PlansScreen from "./screens/plans/PlansScreen";
import ReportsScreen from "./screens/reports/ReportsScreen";
import SellSimScreen from "./screens/sell-sim/SellSimScreen";
import StaffScreen from "./screens/staff/StaffScreen";
import StockScreen from "./screens/stock/StockScreen";
import WalletScreen from "./screens/wallet/WalletScreen";
import PlaceholderScreen from "./screens/PlaceholderScreen";

// URL -> screen map. Everything except /login sits behind RequireAuth.
const router = createBrowserRouter([
  { path: "/login", element: <LoginRoute /> },
  {
    element: <RequireAuth />,
    children: [
      {
        element: <AppShell />,
        children: [
          { index: true, element: <DashboardScreen /> },
          { path: "sales/activate", element: <SellSimScreen /> },
          { path: "lines", element: <LinesScreen /> },
          { path: "lines/:imsi", element: <LineDetailScreen /> },
          { path: "customers", element: <CustomersScreen /> },
          { path: "plans", element: <PlansScreen /> },
          { path: "inventory", element: <StockScreen /> },
          { path: "finance/wallet", element: <WalletScreen /> },
          { path: "finance/reports", element: <ReportsScreen /> },
          { path: "admin/audit", element: <StaffScreen /> },
          { path: "*", element: <PlaceholderScreen title="Page not found" /> },
        ],
      },
    ],
  },
]);

export default function App() {
  return <RouterProvider router={router} />;
}
