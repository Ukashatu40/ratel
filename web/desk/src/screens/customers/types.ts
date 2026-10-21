import type { Customer, KycStatus } from "../sell-sim/types";

export type KycTab = "all" | KycStatus;

export interface CustomerRow extends Customer {
  linesCount: number;
  kycSubmittedAt: number;     // Unix seconds, UTC
  kycSubmittedBy: string;
  linkedIccids: string[];
}

export interface CustomersQuery { q: string; tab: KycTab; page: number; pageSize: number }
// counts are for the current search, one number per tab
export interface CustomersPage { items: CustomerRow[]; total: number; counts: Record<KycTab, number> }

export interface CustomerHistoryEntry { at: number; action: string; actor: string; reason: string }
export interface KycDecision { status: "verified" | "rejected"; reason: string }
