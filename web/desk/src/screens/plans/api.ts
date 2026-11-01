import * as mock from "./mock";
import * as real from "./realApi";
import type { Bundle, BundleInput, Kind, OfferHistoryEntry, PlanFull, PlanInput } from "./types";

// With VITE_USE_MOCK=true everything works on fixture data. Otherwise the screen is read-only: the contract has a plan
// list and nothing to create, edit or retire a plan or bundle, and no staff list of bundles (see realApi.ts).
export const isMock = () => import.meta.env.MODE === "test" || import.meta.env.VITE_USE_MOCK === "true";
export const offersEditable = (): boolean => isMock();
export const bundlesListed = (): boolean => isMock();

const unavailable = () => Promise.reject(new Error("The API has no operation for this yet"));

export const getPlans = (): Promise<PlanFull[]> => (isMock() ? mock.mockGetPlans() : real.getPlans());
export const getBundles = (): Promise<Bundle[]> => (isMock() ? mock.mockGetBundles() : Promise.resolve([]));

// id === null creates; otherwise updates. The value matches the kind (plans have speeds, bundles do not).
export function saveOffer(kind: Kind, id: string | null, value: PlanInput | BundleInput, _key: string): Promise<void> {
  if (!isMock()) return unavailable();
  return kind === "plan" ? mock.mockSavePlan(id, value as PlanInput) : mock.mockSaveBundle(id, value);
}
export const retireOffer = (kind: Kind, id: string, _key: string): Promise<void> => (isMock() ? mock.mockRetire(kind, id) : unavailable());
export const getOfferHistory = (kind: Kind, id: string): Promise<OfferHistoryEntry[]> => (isMock() ? mock.mockOfferHistory(kind, id) : unavailable());
