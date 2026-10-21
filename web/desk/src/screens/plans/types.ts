import type { Plan } from "../sell-sim/types";

export type Kind = "plan" | "bundle";
export type OfferStatus = "on_sale" | "retired";
export const CHANNELS = ["RatelDesk", "RatelPay"]; // ASSUMED values: the Build Plan has a "channels" field but does not list them

export interface PlanFull extends Plan { channels: string[]; status: OfferStatus }
export interface Bundle { bundleId: string; name: string; priceKobo: number; validityDays: number; dataBytes: number; channels: string[]; status: OfferStatus }
export type PlanInput = Omit<PlanFull, "planId" | "status">;
export type BundleInput = Omit<Bundle, "bundleId" | "status">;

export interface OfferHistoryEntry { at: number; action: string; actor: string; detail: string }
