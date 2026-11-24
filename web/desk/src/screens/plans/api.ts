import * as mock from "./mock";
import * as real from "./realApi";
import type { Bundle, BundleInput, CatalogueSettings, Kind, OfferHistoryEntry, PlanFull, PlanInput, SettingsView } from "./types";

// With VITE_USE_MOCK=true everything works on fixture data; otherwise on the catalogue API (docs/catalogue.md).
// Only an admin may change the catalogue: the API answers 403 to anyone else and the screen shows its message.
export const isMock = () => import.meta.env.MODE === "test" || import.meta.env.VITE_USE_MOCK === "true";
export const offersEditable = (): boolean => true;
export const bundlesListed = (): boolean => true;

export const getPlans = (): Promise<PlanFull[]> => (isMock() ? mock.mockGetPlans() : real.getPlans());
export const getBundles = (): Promise<Bundle[]> => (isMock() ? mock.mockGetBundles() : real.getBundles());
export const getSettings = (): Promise<SettingsView> => (isMock() ? mock.mockGetSettings() : real.getSettings());
export const saveSettings = (s: CatalogueSettings, reason: string): Promise<void> => (isMock() ? mock.mockSaveSettings(s) : real.saveSettings(s, reason));

// id === null publishes a new offer. A sold offer is never edited: "saving" an existing one publishes the changed copy
// and retires the old one, so customers keep what they bought.
export async function saveOffer(kind: Kind, id: string | null, value: PlanInput | BundleInput, key: string, reason: string): Promise<void> {
  if (isMock()) return kind === "plan" ? mock.mockSavePlan(id, value as PlanInput) : mock.mockSaveBundle(id, value);
  const newId = await real.createOffer(kind, value, key, reason);
  if (id !== null) await real.retireOffer(kind, id, `${reason} (replaced by #${newId})`, `${key}-retire`);
}
export const retireOffer = (kind: Kind, id: string, key: string, reason: string): Promise<void> =>
  isMock() ? mock.mockRetire(kind, id) : real.retireOffer(kind, id, reason, key);
export const getOfferHistory = (kind: Kind, id: string): Promise<OfferHistoryEntry[]> =>
  isMock() ? mock.mockOfferHistory(kind, id) : real.getOfferHistory(kind, id);
