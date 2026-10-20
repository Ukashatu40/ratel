import { apiGet } from "../../lib/api";
import { mockDashboard } from "./mock";
import type { DashboardData } from "./types";

// While the BSS API is not ready, set VITE_USE_MOCK=true in .env.local to use the fixture data.
export async function getDashboard(): Promise<DashboardData> {
  if (import.meta.env.VITE_USE_MOCK === "true") {
    await new Promise((r) => setTimeout(r, 300)); // feel like a real request
    return mockDashboard;
  }
  return apiGet<DashboardData>("/v1/dashboard"); // TODO: confirm the real endpoint and shape with the RatelBSS developers
}