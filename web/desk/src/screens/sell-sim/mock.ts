import type { ActivateRequest, ActivateResult, Customer, FreeSim, NewCustomer, Plan } from "./types";

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
export const mockNumbers = ["+234 700 000 0150", "+234 700 000 0151", "+234 700 000 0152", "+234 700 000 0153", "+234 700 000 0154"];

export const mockPlans: Plan[] = [
  { planId: "p1", name: "Weekly 2GB", priceKobo: 120_000, validityDays: 7, dataBytes: 2_000_000_000, speedUlMbps: 10, speedDlMbps: 20, onExhaustion: "slow", slowUlMbps: 0.5, slowDlMbps: 1 },
  { planId: "p2", name: "Starter 5GB", priceKobo: 350_000, validityDays: 30, dataBytes: 5_000_000_000, speedUlMbps: 10, speedDlMbps: 20, onExhaustion: "slow", slowUlMbps: 0.5, slowDlMbps: 1 },
  { planId: "p3", name: "Family 20GB", priceKobo: 980_000, validityDays: 30, dataBytes: 20_000_000_000, speedUlMbps: 20, speedDlMbps: 40, onExhaustion: "stop", slowUlMbps: 0, slowDlMbps: 0 },
];

export async function mockActivate(req: ActivateRequest): Promise<ActivateResult> {
  await wait(900);
  const plan = mockPlans.find((p) => p.planId === req.planId)!;
  const sim = mockSims.find((s) => s.iccid === req.iccid);
  return { imsi: sim?.imsi ?? "621000000000150", msisdn: req.msisdn, planName: plan.name, expiresAt: Math.floor(Date.now() / 1000) + plan.validityDays * 86400 };
}
