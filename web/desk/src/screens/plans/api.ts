import { apiGet, apiPost, apiPut } from "../../lib/api";
import { mockGetBundles, mockGetPlans, mockOfferHistory, mockRetire, mockSaveBundle, mockSavePlan } from "./mock";
import type { Bundle, BundleInput, Kind, OfferHistoryEntry, PlanFull, PlanInput } from "./types";

// ASSUMED endpoints (confirm with the RatelBSS developers; only this file should change):
//   GET  /v1/plans  and  GET /v1/bundles                  (all, including retired)
//   POST /v1/plans, PUT /v1/plans/{id}, POST /v1/plans/{id}/retire, GET /v1/plans/{id}/history   (same four for /v1/bundles)
const isMock = () => import.meta.env.VITE_USE_MOCK === "true";
const path = (kind: Kind) => (kind === "plan" ? "/v1/plans" : "/v1/bundles");

export const getPlans = (): Promise<PlanFull[]> => (isMock() ? mockGetPlans() : apiGet<PlanFull[]>("/v1/plans"));
export const getBundles = (): Promise<Bundle[]> => (isMock() ? mockGetBundles() : apiGet<Bundle[]>("/v1/bundles"));

// id === null creates; otherwise updates. The value matches the kind (plans have speeds, bundles do not).
export function saveOffer(kind: Kind, id: string | null, value: PlanInput | BundleInput, key: string): Promise<void> {
  if (isMock()) return kind === "plan" ? mockSavePlan(id, value as PlanInput) : mockSaveBundle(id, value);
  return id === null ? apiPost<void>(path(kind), value, key) : apiPut<void>(`${path(kind)}/${id}`, value, key);
}
export const retireOffer = (kind: Kind, id: string, key: string): Promise<void> => (isMock() ? mockRetire(kind, id) : apiPost<void>(`${path(kind)}/${id}/retire`, {}, key));
export const getOfferHistory = (kind: Kind, id: string): Promise<OfferHistoryEntry[]> =>
  isMock() ? mockOfferHistory(kind, id) : apiGet<OfferHistoryEntry[]>(`${path(kind)}/${id}/history`);
