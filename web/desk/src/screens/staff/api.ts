import { apiGet, apiPost, apiPut } from "../../lib/api";
import { mockCreateStaff, mockGetAudit, mockGetStaff, mockUpdateStaff } from "./mock";
import type { AuditPage, AuditQuery, StaffInput, StaffMember, StaffUpdate } from "./types";

// ASSUMED endpoints (confirm with the RatelBSS developers; only this file should change):
//   GET  /v1/staff                 -> StaffMember[]
//   POST /v1/staff                 { name, email, role, vpnAccess }
//   PUT  /v1/staff/{id}            { role, vpnAccess, active, reason }   (a role or status change needs a reason)
//   GET  /v1/audit?q=&page=&pageSize=  -> { items, total }   (every action across RatelDesk, newest first)
// The backend must enforce who may change staff accounts. The screen only hides the buttons.
const isMock = () => import.meta.env.VITE_USE_MOCK === "true";

export const getStaff = (): Promise<StaffMember[]> => (isMock() ? mockGetStaff() : apiGet<StaffMember[]>("/v1/staff"));
export const createStaff = (input: StaffInput, key: string): Promise<void> => (isMock() ? mockCreateStaff(input) : apiPost<void>("/v1/staff", input, key));
export const updateStaff = (id: string, update: StaffUpdate, key: string): Promise<void> => (isMock() ? mockUpdateStaff(id, update) : apiPut<void>(`/v1/staff/${id}`, update, key));
export const getAudit = (q: AuditQuery): Promise<AuditPage> =>
  isMock() ? mockGetAudit(q) : apiGet<AuditPage>(`/v1/audit?${new URLSearchParams({ q: q.q, page: String(q.page), pageSize: String(q.pageSize) })}`);
