import { ApiError } from "../../lib/api";
import type { AuditEntry, AuditPage, AuditQuery, StaffInput, StaffMember, StaffUpdate } from "./types";

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));
const nowSec = () => Math.floor(Date.now() / 1000);
const ACTOR = "Amina Yusuf";

const staff: StaffMember[] = [
  { id: "s1", name: "Amina Yusuf", email: "amina.yusuf@ratelplus.example", role: "Customer Care", vpnAccess: true, active: true, lastSignInAt: nowSec() - 2400 },
  { id: "s2", name: "Bashir Aliyu", email: "bashir.aliyu@ratelplus.example", role: "Customer Care", vpnAccess: true, active: true, lastSignInAt: nowSec() - 3 * 3600 },
  { id: "s3", name: "Ibrahim Danladi", email: "ibrahim.danladi@ratelplus.example", role: "Super Admin", vpnAccess: false, active: true, lastSignInAt: nowSec() - 86400 },
  { id: "s4", name: "Ratelplus Admin", email: "admin@ratelplus.example", role: "Super Admin", vpnAccess: true, active: true, lastSignInAt: nowSec() - 2 * 86400 },
  { id: "s5", name: "Khadija Umar", email: "khadija.umar@ratelplus.example", role: "Customer Care", vpnAccess: false, active: false, lastSignInAt: nowSec() - 40 * 86400 },
];

// The audit log across all of RatelDesk. Built from templates here; the real one comes from the backend.
const TEMPLATES: [string, string, string][] = [
  ["Line suspended", "+234 700 000 0127", "Customer request"], ["KYC approved", "Fatima Bello", "NIN matches the customer's details"],
  ["Plan edited", "Starter 5GB", "price_kobo 300000 to 350000"], ["Voucher card locked", "•••• 4821", "Lost card"],
  ["SIM batch imported", "SIM-2026-007", "2,000 SIMs"], ["KYC rejected", "Sani Danjuma", "Name does not match NIN record"],
  ["Voucher batch approved", "B-2026-015", "Batch approved for printing"], ["Plan retired", "Promo 1GB", "Campaign ended"],
];
const NAMES = ["Amina Yusuf", "Bashir Aliyu", "Ibrahim Danladi"];
const audit: AuditEntry[] = Array.from({ length: 64 }, (_, i) => {
  const [action, target, reason] = TEMPLATES[(i * 3) % TEMPLATES.length];
  return { id: "", at: nowSec() - 3600 * (2 + i * 9), actor: NAMES[i % 3], action, target, reason };
});
const log = (action: string, target: string, reason: string) => audit.unshift({ id: "", at: nowSec(), actor: ACTOR, action, target, reason });
const withIds = () => audit.map((e, i) => ({ ...e, id: `A-${audit.length - i}` }));

export async function mockGetStaff(): Promise<StaffMember[]> { await wait(200); return staff.map((s) => ({ ...s })); }

export async function mockCreateStaff(input: StaffInput): Promise<void> {
  await wait(400);
  if (staff.some((s) => s.email.toLowerCase() === input.email.toLowerCase())) throw new Error("A staff account with that email already exists");
  staff.push({ ...input, id: `s${staff.length + 1}`, active: true, lastSignInAt: null });
  log("Staff account created", input.name, `${input.role}, ${input.vpnAccess ? "VPN access" : "office only"}`);
}

export async function mockUpdateStaff(id: string, u: StaffUpdate): Promise<void> {
  await wait(400);
  const i = staff.findIndex((s) => s.id === id);
  if (i < 0) throw new ApiError(404, "staff_not_found", "No such staff member");
  const old = staff[i], changes: string[] = [];
  if (u.role !== old.role) changes.push(`role ${old.role} to ${u.role}`);
  if (u.vpnAccess !== old.vpnAccess) changes.push(u.vpnAccess ? "VPN access on" : "VPN access off");
  if (u.active !== old.active) changes.push(u.active ? "account enabled" : "account disabled");
  if ((u.role !== old.role || u.active !== old.active) && u.reason.trim().length < 3) throw new ApiError(422, "reason_required", "A reason is required to change a role or disable an account");
  staff[i] = { ...old, role: u.role, vpnAccess: u.vpnAccess, active: u.active };
  if (changes.length) log("Staff account changed", old.name, `${changes.join(", ")}${u.reason.trim() ? `: ${u.reason.trim()}` : ""}`);
}

export async function mockGetAudit({ q, page, pageSize }: AuditQuery): Promise<AuditPage> {
  await wait(200);
  const s = q.trim().toLowerCase();
  const rows = withIds().filter((e) => !s || `${e.actor} ${e.action} ${e.target} ${e.reason}`.toLowerCase().includes(s));
  return { items: rows.slice((page - 1) * pageSize, page * pageSize), total: rows.length };
}
