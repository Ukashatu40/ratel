import { customerFromRow, customerFromWire, type WireCustomer, type WireCustomerRow } from "../sell-sim/contract";
import type { CustomerHistoryEntry, CustomerRow, CustomersPage, KycDecision, KycTab } from "./types";

// The wire shapes of the customers screens (contracts/openapi.yaml) and their mappers.
// tests/fixtures/contract/CustomerList.json, Customer.created.json and CustomerHistory.json are checked against the contract.

export interface WireCustomerList { customers: WireCustomerRow[]; total: number; counts: Record<KycTab, number> }
export interface WireCustomerHistoryEntry { at: number; action: "registered" | "kyc_verified" | "kyc_rejected"; actor: string; reason: string }
export interface WireCustomerHistory { entries: WireCustomerHistoryEntry[]; total: number }

export const customerRowFromWire = (r: WireCustomerRow): CustomerRow => ({ ...customerFromRow(r), linesCount: r.lines_count });

export const customersPageFromWire = (w: WireCustomerList): CustomersPage => ({
  items: w.customers.map(customerRowFromWire), total: w.total, counts: w.counts,
});

export { customerFromWire };
export type { WireCustomer };

const ACTION_LABEL: Record<WireCustomerHistoryEntry["action"], string> = {
  registered: "Customer registered", kyc_verified: "KYC verified", kyc_rejected: "KYC rejected",
};
// `actor` is staff:<id> for now (TODO(contract): whether RatelDesk shows a name instead).
export const customerHistoryFromWire = (h: WireCustomerHistory): CustomerHistoryEntry[] =>
  h.entries.map((e) => ({ at: e.at, action: ACTION_LABEL[e.action] ?? e.action, actor: e.actor, reason: e.reason }));

export const toWireKyc = (d: KycDecision) => ({ status: d.status, reason: d.reason.trim() });
