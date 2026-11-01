import { apiGet } from "../../lib/api";
import type { WirePlan } from "../sell-sim/contract";
import { planFullFromWire } from "./contract";
import type { PlanFull } from "./types";

// The only plan operation the contract has is the list, and it lists the plans on sale.
// TODO(contract): creating, editing and retiring plans and bundles, a bundle list for staff, and a plan's history.
// Until they exist, those are done with ops_cli on bss-app (deploy/bss-app/README.md), and this screen is read-only.
export const getPlans = (): Promise<PlanFull[]> =>
  apiGet<{ plans: WirePlan[] }>("/v1/plans").then((r) => r.plans.map(planFullFromWire));
