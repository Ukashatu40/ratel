import { ApiError } from "../../lib/api";
import { formatNaira } from "../../lib/format";
import { mockAddLine, mockFindLine, mockNextLineId, mockSetLineState } from "../lines/mock";
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

// ---- the sale: wallets in memory, and the lines themselves in the lines mock, so the whole journey runs without a backend ----
interface MockWallet { balanceKobo: number; bought: boolean }
const wallets = new Map<number, MockWallet>();

// Any line has a wallet; a line the mock already had starts with an empty one.
const walletOf = (lineId: number): MockWallet => {
  if (!mockFindLine(lineId)) throw new ApiError(404, "not_found", "No such line");
  if (!wallets.has(lineId)) wallets.set(lineId, { balanceKobo: 0, bought: false });
  return wallets.get(lineId)!;
};
const planOf = (planId: string): Plan => mockPlans.find((p) => p.planId === planId)!;

export async function mockCreateLine(req: CreateLineRequest): Promise<CreatedLine> {
  await wait(500);
  const sim = mockSims.find((s) => s.iccid === req.iccid);
  const customer = mockCustomers.find((c) => c.id === req.customerId);
  const lineId = mockNextLineId();
  const imsi = sim?.imsi ?? "621000000000150";
  mockAddLine({
    lineId, planId: req.planId, imsi, iccid: req.iccid, msisdn: req.msisdn, customerName: customer?.name ?? "Customer",
    planName: planOf(req.planId).name, state: "awaiting_activation", planEndsEpoch: null,
  });
  wallets.set(lineId, { balanceKobo: 0, bought: false });
  return { lineId, imsi, msisdn: req.msisdn, planId: req.planId, state: "awaiting_activation", expiresAt: null };
}

export async function mockGetWallet(lineId: number): Promise<Wallet> {
  await wait(200);
  const w = walletOf(lineId);
  return { balanceKobo: w.balanceKobo, ledgerSumKobo: w.balanceKobo };
}

// Mock only: stands in for the customer redeeming a prepaid card on the RatelPay page.
export function mockTopUp(lineId: number, kobo: number): void {
  walletOf(lineId).balanceKobo += kobo;
}

export async function mockBuyPlan(lineId: number, planId: string): Promise<Purchase> {
  await wait(400);
  const w = walletOf(lineId);
  const plan = planOf(planId);
  if (w.bought) return { priceKobo: plan.priceKobo, netKobo: 0, vatKobo: 0, balanceKobo: w.balanceKobo, validTo: null, replayed: true };
  if (w.balanceKobo < plan.priceKobo) {
    throw new ApiError(409, "insufficient_funds", `The wallet is short by ${formatNaira(plan.priceKobo - w.balanceKobo)}`);
  }
  w.balanceKobo -= plan.priceKobo;
  w.bought = true;
  const net = Math.round((plan.priceKobo * 1000) / 1075); // 7.5% VAT inside the price
  return { priceKobo: plan.priceKobo, netKobo: net, vatKobo: plan.priceKobo - net, balanceKobo: w.balanceKobo, validTo: Math.floor(Date.now() / 1000) + plan.validityDays * 86400, replayed: false };
}

export async function mockActivateLine(lineId: number): Promise<CreatedLine> {
  await wait(700);
  const w = walletOf(lineId);
  const line = mockFindLine(lineId)!;
  if (!w.bought) throw new ApiError(409, "conflict", "The line has no paid-for allowance yet");
  const expiresAt = Math.floor(Date.now() / 1000) + planOf(line.planId).validityDays * 86400;
  mockSetLineState(lineId, "active", expiresAt);
  return { lineId, imsi: line.imsi, msisdn: line.msisdn, planId: line.planId, state: "active", expiresAt };
}

// A plan by id, whatever its state: the line page needs the price of the plan a line is waiting on.
export const mockGetPlan = async (planId: string): Promise<Plan | null> => mockPlans.find((p) => p.planId === planId) ?? null;
