import { apiGet, apiPost, apiPut } from "../../lib/api";
import {
  bundleFromOffer, historyFromWire, planFromOffer, settingsToWire, settingsViewFromWire,
  type WireAuditPage, type WireCatalogue, type WireSettings,
} from "./contract";
import type { Bundle, BundleInput, CatalogueSettings, Kind, OfferHistoryEntry, PlanFull, PlanInput, SettingsView } from "./types";

// The catalogue an admin keeps (docs/catalogue.md): GET /v1/catalogue lists everything, on sale and retired.
const catalogue = () => apiGet<WireCatalogue>("/v1/catalogue");

export const getPlans = (): Promise<PlanFull[]> => catalogue().then((c) => c.offers.filter((o) => o.kind === "plan").map(planFromOffer));
export const getBundles = (): Promise<Bundle[]> => catalogue().then((c) => c.offers.filter((o) => o.kind === "bundle").map(bundleFromOffer));
export const getSettings = (): Promise<SettingsView> => catalogue().then(settingsViewFromWire);

export async function createOffer(kind: Kind, value: PlanInput | BundleInput, key: string, reason: string): Promise<string> {
  const plan = kind === "plan" ? (value as PlanInput) : null;
  const body = {
    kind, name: value.name, price_kobo: value.priceKobo, data_bytes: value.dataBytes, validity_days: value.validityDays, channels: value.channels, reason,
    ...(plan && {
      speed_dl_mbps: plan.speedDlMbps, speed_ul_mbps: plan.speedUlMbps, on_exhaustion: plan.onExhaustion,
      ...(plan.onExhaustion === "slow" && { slow_dl_mbps: plan.slowDlMbps, slow_ul_mbps: plan.slowUlMbps }),
    }),
  };
  const created = await apiPost<{ offer_id: number }>("/v1/catalogue/offers", body, key);
  return String(created.offer_id);
}

export const retireOffer = (kind: Kind, id: string, reason: string, key: string): Promise<void> =>
  apiPost<{ retired: boolean }>(`/v1/catalogue/offers/${kind}/${id}/retire`, { reason }, key).then(() => undefined);

export const getOfferHistory = (kind: Kind, id: string): Promise<OfferHistoryEntry[]> =>
  apiGet<WireAuditPage>("/v1/catalogue/audit?limit=200").then((page) => historyFromWire(page, kind, id));

export const saveSettings = (settings: CatalogueSettings, reason: string): Promise<void> =>
  apiPut<WireSettings>("/v1/catalogue/settings", { ...settingsToWire(settings), reason }).then(() => undefined);
