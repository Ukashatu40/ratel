import { planFromWire, type WirePlan } from "../sell-sim/contract";
import type { Bundle, CatalogueSettings, OfferHistoryEntry, PlanFull, SettingsView } from "./types";

// A plan from GET /v1/plans (Sell SIM's list). Its `channels` is one stored string.
export const planFullFromWire = (p: WirePlan): PlanFull => ({
  ...planFromWire(p), channels: p.channels ? p.channels.split(",").filter(Boolean) : [], status: p.state,
});

// GET /v1/catalogue (contract schema Catalogue).
export interface WireOffer {
  kind: "plan" | "bundle"; offer_id: number; name: string; price_kobo: number; data_bytes: number; validity_days: number;
  channels: string[]; state: string; speed_dl_mbps: number | null; speed_ul_mbps: number | null; on_exhaustion: string | null;
  slow_dl_mbps: number | null; slow_ul_mbps: number | null;
}
export interface WireSettings {
  airtime_min_kobo: number; card_min_kobo: number; card_max_kobo: number; airtime_presets_kobo: number[];
  voice_onnet_kobo_per_min: number; voice_offnet_kobo_per_min: number; sms_onnet_kobo: number; voucher_values_kobo: number[];
}
export interface WireCatalogue { offers: WireOffer[]; settings: WireSettings; gateway: { min_kobo: number; max_kobo: number }; channels: string[] }
export interface WireAuditPage { items: { audit_id: number; actor: string; action: string; offer_kind: string | null; offer_id: number | null; reason: string; detail: string; at: number | null }[] }

const status = (s: string) => (s === "on_sale" ? "on_sale" : "retired") as PlanFull["status"];

export const planFromOffer = (o: WireOffer): PlanFull => ({
  planId: String(o.offer_id), name: o.name, priceKobo: o.price_kobo, validityDays: o.validity_days, dataBytes: o.data_bytes,
  speedUlMbps: o.speed_ul_mbps ?? 0, speedDlMbps: o.speed_dl_mbps ?? 0, onExhaustion: o.on_exhaustion === "slow" ? "slow" : "stop",
  slowUlMbps: o.slow_ul_mbps ?? 0, slowDlMbps: o.slow_dl_mbps ?? 0, channels: o.channels, status: status(o.state),
});
export const bundleFromOffer = (o: WireOffer): Bundle => ({
  bundleId: String(o.offer_id), name: o.name, priceKobo: o.price_kobo, validityDays: o.validity_days, dataBytes: o.data_bytes,
  channels: o.channels, status: status(o.state),
});
export const settingsFromWire = (s: WireSettings): CatalogueSettings => ({
  airtimeMinKobo: s.airtime_min_kobo, cardMinKobo: s.card_min_kobo, cardMaxKobo: s.card_max_kobo, presetsKobo: s.airtime_presets_kobo,
  onnetKoboPerMin: s.voice_onnet_kobo_per_min, offnetKoboPerMin: s.voice_offnet_kobo_per_min, smsOnnetKobo: s.sms_onnet_kobo, voucherValuesKobo: s.voucher_values_kobo,
});
export const settingsToWire = (s: CatalogueSettings): WireSettings => ({
  airtime_min_kobo: s.airtimeMinKobo, card_min_kobo: s.cardMinKobo, card_max_kobo: s.cardMaxKobo, airtime_presets_kobo: s.presetsKobo,
  voice_onnet_kobo_per_min: s.onnetKoboPerMin, voice_offnet_kobo_per_min: s.offnetKoboPerMin, sms_onnet_kobo: s.smsOnnetKobo, voucher_values_kobo: s.voucherValuesKobo,
});
export const settingsViewFromWire = (c: WireCatalogue): SettingsView => ({
  settings: settingsFromWire(c.settings), gateway: { minKobo: c.gateway.min_kobo, maxKobo: c.gateway.max_kobo },
});

const ACTION: Record<string, string> = {
  create_plan: "Plan published", create_bundle: "Bundle published", retire_plan: "Plan retired", retire_bundle: "Bundle retired", update_settings: "Settings saved",
};
export const historyFromWire = (page: WireAuditPage, kind: string, id: string): OfferHistoryEntry[] =>
  page.items
    .filter((i) => i.offer_kind === kind && String(i.offer_id) === id)
    .map((i) => ({ at: i.at ?? 0, action: ACTION[i.action] ?? i.action, actor: i.actor, detail: [i.reason, i.detail].filter(Boolean).join(" | ") }))
    .reverse(); // oldest first, like the mock
