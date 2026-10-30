import type { AuthUser } from "../../lib/authContext";

export type Role = AuthUser["role"]; // "Customer Care" | "Super Admin"
export const ROLES: Role[] = ["Customer Care", "Super Admin"];

export interface StaffMember {
  id: string;
  name: string;
  email: string;                // the sign-in name, fixed after the account is created
  role: Role;
  vpnAccess: boolean;           // false = can only use RatelDesk from the office network
  active: boolean;
  lastSignInAt: number | null;  // Unix seconds, UTC
}
export interface StaffInput { name: string; email: string; role: Role; vpnAccess: boolean }
export interface StaffUpdate { role: Role; vpnAccess: boolean; active: boolean; reason: string } // a role or status change needs a reason

export interface AuditEntry { id: string; at: number; actor: string; action: string; target: string; reason: string }
export interface AuditPage { items: AuditEntry[]; total: number }
export interface AuditQuery { q: string; page: number; pageSize: number }
