import { planFromWire, type WirePlan } from "../sell-sim/contract";
import type { PlanFull } from "./types";

// A plan as the plans screen shows it. The contract's `channels` is one string whose representation is still
// TODO(PRD), so it is shown as it comes and not split.
export const planFullFromWire = (p: WirePlan): PlanFull => ({
  ...planFromWire(p), channels: p.channels ? [p.channels] : [], status: p.state,
});
