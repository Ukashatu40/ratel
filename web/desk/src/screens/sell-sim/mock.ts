import { ApiError } from "../../lib/api";
import { formatNaira } from "../../lib/format";
import type { CreatedLine, CreateLineRequest, Customer, FreeSim, NewCustomer, Plan, Purchase, Wallet } from "./types";

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));

// PRD SECURITY_AND_PRIVACY: personal data (NIN, etc.) never appears in the repository. These are demo placeholders.
export const mockCustomers: Customer[] = [
  { id: "c1", name: "Aisha Sani", phone: "+234 803 000 0000", email: "aisha.s@mail.example", idType: "NIN", idNumber: "DEMO0000001", address: "12 Yakubu Gowon Way, Kaduna", kycStatus: "pending", blocked: false },
  { id: "c2", name: "Fatima Bello", phone: "+234 806 111 2222", email: "f.bello@mail.example", idType: "NIN", idNumber: "DEMO0000002", address: "5 Ahmadu Bello Way, Kano", kycStatus: "verified", blocked: false },
  { id: "c3", name: "Musa Ibrahim", phone: "+234 701 222 3333", email: "musa.i@mail.example", idType: "NIN", idNumber: "DEMO0000003", address: "8 Murtala Road, Zaria", kycStatus: "verified", blocked: false },
  { id: "c4", name: "Sani Danjuma", phone: "+234 809 666 7777", email: "sani.d@mail.example", idType: "NIN", idNumber: "DEMO0000004", address: "3 Race Course Road, Kaduna", kycStatus: "rejected", blocked: true },
];

export async function mockSearchCustomers(q: string): Promise<Customer[]> {
  await wait(250);
  const s = q.trim().toLowerCase();
  const digits = s.replace(/\s/g, "");
  return mockCustomers.filter((c) => c.name.toLowerCase().includes(s) || c.phone.replace(/\s/g, "").includes(digits) || c.idNumber.includes(digits));
}

export async function mockCreateCustomer(input: NewCustomer): Promise<Customer> {
  await wait(400);
  const c: Customer = { ...input, id: `c${mockCustomers.length + 1}`, kycStatus: "pending", blocked: false };
  mockCustomers.push(c);
  return c;
}

export const mockSims: FreeSim[] = [0, 1, 2, 3, 4, 5].map((i) => ({ iccid: `89234000000000${12345 + i}`, imsi: `6210000000001${50 + i}`, batch: "SIM-2026-007" }));
export const mockNumbers = ["2347000000150", "2347000000151", "2347000000152", "2347000000153", "2347000000154"]; // the stored form: digits, international, no plus

export const mockPlans: Plan[] = [
  { planId: "1", name: "Weekly 2GB", priceKobo: 120_000, validityDays: 7, dataBytes: 2_000_000_000, speedUlMbps: 10, speedDlMbps: 20, onExhaustion: "slow", slowUlMbps: 0.5, slowDlMbps: 1 },
  { planId: "2", name: "Starter 5GB", priceKobo: 350_000, validityDays: 30, dataBytes: 5_000_000_000, speedUlMbps: 10, speedDlMbps: 20, onExhaustion: "slow", slowUlMbps: 0.5, slowDlMbps: 1 },
  { planId: "3", name: "Family 20GB", priceKobo: 980_000, validityDays: 30, dataBytes: 20_000_000_000, speedUlMbps: 20, speedDlMbps: 40, onExhaustion: "stop", slowUlMbps: 0, slowDlMbps: 0 },
];

// ---- the sale: an in-memory line and wallet, so the whole journey runs without a backend ----
interface MockLine { line: CreatedLine; balanceKobo: number; bought: boolean }
const mockLines = new Map<number, MockLine>();
let nextLineId = 1;

const need = (lineId: number): MockLine => {
  const m = mockLines.get(lineId);
  if (!m) throw new ApiError(404, "not_found", "No such line");
  return m;
};
const planOf = (planId: string): Plan => mockPlans.find((p) => p.planId === planId)!;

export async function mockCreateLine(req: CreateLineRequest): Promise<CreatedLine> {
  await wait(500);
  const sim = mockSims.find((s) => s.iccid === req.iccid);
  const line: CreatedLine = { lineId: nextLineId++, imsi: sim?.imsi ?? "621000000000150", msisdn: req.msisdn, planId: req.planId, state: "awaiting_activation", expiresAt: null };
  mockLines.set(line.lineId, { line, balanceKobo: 0, bought: false });
  return line;
}

export async function mockGetWallet(lineId: number): Promise<Wallet> {
  await wait(200);
  const m = need(lineId);
  return { balanceKobo: m.balanceKobo, ledgerSumKobo: m.balanceKobo };
}

// Mock only: stands in for the customer redeeming a prepaid card on the RatelPay page.
export function mockTopUp(lineId: number, kobo: number): void {
  need(lineId).balanceKobo += kobo;
}

export async function mockBuyPlan(lineId: number, planId: string): Promise<Purchase> {
  await wait(400);
  const m = need(lineId);
  const plan = planOf(planId);
  if (m.bought) return { priceKobo: plan.priceKobo, netKobo: 0, vatKobo: 0, balanceKobo: m.balanceKobo, validTo: null, replayed: true };
  if (m.balanceKobo < plan.priceKobo) {
    throw new ApiError(409, "insufficient_funds", `The wallet is short by ${formatNaira(plan.priceKobo - m.balanceKobo)}`);
  }
  m.balanceKobo -= plan.priceKobo;
  m.bought = true;
  const net = Math.round((plan.priceKobo * 1000) / 1075); // 7.5% VAT inside the price
  return { priceKobo: plan.priceKobo, netKobo: net, vatKobo: plan.priceKobo - net, balanceKobo: m.balanceKobo, validTo: Math.floor(Date.now() / 1000) + plan.validityDays * 86400, replayed: false };
}

export async function mockActivateLine(lineId: number): Promise<CreatedLine> {
  await wait(700);
  const m = need(lineId);
  if (!m.bought) throw new ApiError(409, "conflict", "The line has no paid-for allowance yet");
  m.line = { ...m.line, state: "active", expiresAt: Math.floor(Date.now() / 1000) + planOf(m.line.planId).validityDays * 86400 };
  return m.line;
}
