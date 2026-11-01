import { apiGet } from "../../lib/api";
import { dashboardFromWire, type WireDashboard } from "./contract";
import { mockDashboard } from "./mock";
import type { DashboardData } from "./types";

// With VITE_USE_MOCK=true this returns fixture data. Otherwise it calls GET /v1/dashboard (contract.ts maps the answer).
export async function getDashboard(): Promise<DashboardData> {
  if (import.meta.env.MODE === "test" || import.meta.env.VITE_USE_MOCK === "true") {
    await new Promise((r) => setTimeout(r, 300)); // feel like a real request
    return mockDashboard;
  }
  return dashboardFromWire(await apiGet<WireDashboard>("/v1/dashboard"));
}
