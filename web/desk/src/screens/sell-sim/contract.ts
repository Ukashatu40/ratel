import type { Customer, CreatedLine, CreateLineRequest, FreeSim, NewCustomer, Plan, Purchase, Wallet } from "./types";
import type { LineState } from "../dashboard/types";

// The wire shapes of the sell journey, as contracts/openapi.yaml defines them (snake_case, integer ids),
// and the mappers to the Desk's own types. The contract wins: when it changes, this file changes with it.
// tests/fixtures/contract/*.json hold example bodies that tests/contract/test_desk_fixtures.py checks
// against the contract, and tests/sell-contract.test.ts checks these mappers against them.

export interface WireCustomerRow { customer_id: number; name: string; phone: string; email: string; kyc_status: "pending" | "verified" | "rejected"; blocked: boolean; lines_count: number }
export interface WireCustomer { customer_id: number; name: string; phone: string; email: string; id_type: string; id_number: string; address: string; kyc_status: "pending" | "verified" | "rejected"; blocked: boolean }
export interface WireSim { iccid: string; imsi: string; batch: string; state: "in_stock" | "in_use" | "retired" }
export interface WireNumber { msisdn: string; state: "available" | "in_use" | "quarantined" }
export interface WirePlan {
  plan_id: number; name: string; price_kobo: number; validity_days: number; data_bytes: number;
  speed_ul_mbps: number; speed_dl_mbps: number; slow_ul_mbps: number; slow_dl_mbps: number;
  channels: string; on_exhaustion: "slow" | "stop"; state: "on_sale" | "retired";
}
export interface WireLine { line_id: number; customer_id: number; iccid: string; imsi: string; msisdn: string; plan_id: number; state: LineState; state_before_suspension?: string | null; expires_at?: number | null }
export interface WireLineWallet { line_id: number; balance_kobo: number; ledger_sum_kobo: number }
export interface WirePurchase { price_kobo: number; net_kobo: number; vat_kobo: number; balance_kobo: number; valid_to: number | null; replayed: boolean }

// The Desk keeps ids as strings; the contract wants integers. A value that is not a whole number is a bug
// (for example a mock id reaching the real API), so it stops here instead of reaching the server.
export function wireId(id: string): number {
  const n = Number(id);
  if (!Number.isSafeInteger(n) || n < 1) throw new Error("This record has no valid id yet.");
  return n;
}

export const customerFromRow = (r: WireCustomerRow): Customer => ({
  id: String(r.customer_id), name: r.name, phone: r.phone, email: r.email,
  idType: "NIN", idNumber: "", address: "", // a list row carries neither the NIN nor the address
  kycStatus: r.kyc_status, blocked: r.blocked,
});

export const customerFromWire = (c: WireCustomer): Customer => ({
  id: String(c.customer_id), name: c.name, phone: c.phone, email: c.email,
  idType: "NIN", // TODO(PRD): allowed id_type values are open (decision 3). Demo value: NIN only.
  idNumber: c.id_number, address: c.address, kycStatus: c.kyc_status, blocked: c.blocked,
});

// A new customer always starts with KYC pending; an admin decides it later.
export const toWireNewCustomer = (c: NewCustomer) => ({
  name: c.name, phone: c.phone, email: c.email, id_type: c.idType, id_number: c.idNumber, address: c.address, kyc_status: "pending" as const,
});

export const simFromWire = (s: WireSim): FreeSim => ({ iccid: s.iccid, imsi: s.imsi, batch: s.batch });

export const planFromWire = (p: WirePlan): Plan => ({
  planId: String(p.plan_id), name: p.name, priceKobo: p.price_kobo, validityDays: p.validity_days, dataBytes: p.data_bytes,
  speedUlMbps: p.speed_ul_mbps, speedDlMbps: p.speed_dl_mbps, onExhaustion: p.on_exhaustion, slowUlMbps: p.slow_ul_mbps, slowDlMbps: p.slow_dl_mbps,
});

export const toWireCreateLine = (r: CreateLineRequest) => ({ customer_id: wireId(r.customerId), iccid: r.iccid, msisdn: r.msisdn, plan_id: wireId(r.planId) });

export const lineFromWire = (l: WireLine): CreatedLine => ({
  lineId: l.line_id, imsi: l.imsi, msisdn: l.msisdn, planId: String(l.plan_id), state: l.state, expiresAt: l.expires_at ?? null,
});

export const walletFromWire = (w: WireLineWallet): Wallet => ({ balanceKobo: w.balance_kobo, ledgerSumKobo: w.ledger_sum_kobo });

export const purchaseFromWire = (p: WirePurchase): Purchase => ({
  priceKobo: p.price_kobo, netKobo: p.net_kobo, vatKobo: p.vat_kobo, balanceKobo: p.balance_kobo, validTo: p.valid_to, replayed: p.replayed,
});
