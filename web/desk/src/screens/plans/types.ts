import type { Plan } from "../sell-sim/types";

export type Kind = "plan" | "bundle";
export type OfferStatus = "on_sale" | "retired";
// Where an offer is sold (docs/catalogue.md). The API's names, with the words staff read.
export const CHANNELS = ["desk", "pay", "sms", "ussd"] as const;
export const CHANNEL_LABEL: Record<string, string> = { desk: "RatelDesk", pay: "RatelPay page", sms: "SMS 555", ussd: "USSD *123#" };

export interface PlanFull extends Plan { channels: string[]; status: OfferStatus }
export interface Bundle { bundleId: string; name: string; priceKobo: number; validityDays: number; dataBytes: number; channels: string[]; status: OfferStatus }
export type PlanInput = Omit<PlanFull, "planId" | "status">;
export type BundleInput = Omit<Bundle, "bundleId" | "status">;

export interface OfferHistoryEntry { at: number; action: string; actor: string; detail: string }

// Airtime limits, call rates and the SMS price, in whole kobo (docs/catalogue.md).
export interface CatalogueSettings {
  airtimeMinKobo: number; cardMinKobo: number; cardMaxKobo: number; presetsKobo: number[];
  onnetKoboPerMin: number; offnetKoboPerMin: number; smsOnnetKobo: number;
}
export interface SettingsView { settings: CatalogueSettings; gateway: { minKobo: number; maxKobo: number } }
