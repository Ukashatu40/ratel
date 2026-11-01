import type { Customer, KycStatus } from "../sell-sim/types";

export type KycTab = "all" | KycStatus;

// A row of the list carries no NIN and no address (they are read one customer at a time).
export interface CustomerRow extends Customer { linesCount: number }

export interface CustomersQuery { q: string; tab: KycTab; page: number; pageSize: number }
// counts are for the current search, one number per tab
export interface CustomersPage { items: CustomerRow[]; total: number; counts: Record<KycTab, number> }

export interface CustomerHistoryEntry { at: number; action: string; actor: string; reason: string }
export interface KycDecision { status: "verified" | "rejected"; reason: string }

// The moves the API allows (bss_decide_kyc): pending to verified or rejected, and rejected to verified.
// Anything else answers 409, and only an admin may decide.
export const kycMovesFrom = (status: KycStatus): KycDecision["status"][] =>
  status === "pending" ? ["verified", "rejected"] : status === "rejected" ? ["verified"] : [];
