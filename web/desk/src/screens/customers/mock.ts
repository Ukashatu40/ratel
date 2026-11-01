import { ApiError } from "../../lib/api";
import { mockCustomers } from "../sell-sim/mock";
import { kycMovesFrom } from "./types";
import type { Customer } from "../sell-sim/types";
import type { CustomerHistoryEntry, CustomerRow, CustomersPage, CustomersQuery, KycDecision } from "./types";

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));
const nowSec = () => Math.floor(Date.now() / 1000);
const FIRST = ["Khadija", "Abubakar", "Halima", "Garba", "Rabi", "Nura", "Amina", "Usman", "Hadiza", "Kabiru", "Maryam", "Yusuf", "Zainab"];
const LAST = ["Umar", "Yahaya", "Musa", "Shehu", "Adamu", "Salisu", "Kabir", "Idris", "Lawan", "Sule", "Tijani", "Bello"];
const CITIES = ["Kano", "Kaduna", "Zaria", "Katsina", "Sokoto", "Bauchi"];

// Make the shared customer list bigger (once), so paging and filters have something to show.
// PRD SECURITY_AND_PRIVACY: use placeholders, never real-looking NINs.
if (mockCustomers.length < 10) {
  for (let i = 0; i < 26; i++) {
    mockCustomers.push({
      id: `c${mockCustomers.length + 1}`, name: `${FIRST[i % FIRST.length]} ${LAST[(i * 5) % LAST.length]}`,
      phone: `+234 80${i % 10} ${100 + i} ${String(1000 + i * 7).slice(-4)}`, email: i % 4 === 0 ? "" : `customer${i}@mail.example`,
      idType: "NIN", idNumber: `DEMO${String(1000000 + i * 777).padStart(7, "0")}`, address: `${i + 1} Market Road, ${CITIES[i % CITIES.length]}`,
      kycStatus: i % 5 === 0 ? "pending" : i % 11 === 0 ? "rejected" : "verified", blocked: false,
    });
  }
}

const indexOf = (c: Customer) => mockCustomers.findIndex((x) => x.id === c.id);
// A list row has neither the NIN nor the address, like the API's.
function toRow(c: Customer): CustomerRow {
  const i = indexOf(c), lines = c.kycStatus === "verified" ? 1 + (i % 3 === 0 ? 1 : 0) : c.id === "c1" ? 1 : 0;
  return { ...c, idNumber: "", address: "", linesCount: lines };
}
const find = (id: string) => {
  const c = mockCustomers.find((x) => x.id === id);
  if (!c) throw new ApiError(404, "customer_not_found", "No such customer");
  return c;
};

const store = new Map<string, CustomerHistoryEntry[]>();
function historyFor(c: Customer): CustomerHistoryEntry[] {
  let h = store.get(c.id);
  if (!h) {
    const i = indexOf(c), base = nowSec() - 86400 * ((i % 20) + 2);
    h = [{ at: base, action: "Customer registered", actor: `staff:${(i % 3) + 1}`, reason: "Registered at the counter" }];
    if (c.kycStatus === "verified") h.push({ at: base + 5 * 3600, action: "KYC verified", actor: "staff:1", reason: "NIN matches the customer's details" });
    if (c.kycStatus === "rejected") h.push({ at: base + 5 * 3600, action: "KYC rejected", actor: "staff:1", reason: "Name does not match NIN record" });
    store.set(c.id, h);
  }
  return h;
}

export async function mockGetCustomers({ q, tab, page, pageSize }: CustomersQuery): Promise<CustomersPage> {
  await wait(200);
  const s = q.trim().toLowerCase(), digits = s.replace(/\D/g, "");
  const found = s ? mockCustomers.filter((c) => c.name.toLowerCase().includes(s) || c.email.toLowerCase().includes(s) || (digits !== "" && c.phone.replace(/\D/g, "").includes(digits))) : mockCustomers;
  const count = (t: CustomersQuery["tab"]) => (t === "all" ? found.length : found.filter((c) => c.kycStatus === t).length);
  const shown = tab === "all" ? found : found.filter((c) => c.kycStatus === tab);
  return { items: shown.slice((page - 1) * pageSize, page * pageSize).map(toRow), total: shown.length, counts: { all: count("all"), pending: count("pending"), verified: count("verified"), rejected: count("rejected") } };
}

export async function mockGetCustomer(id: string): Promise<Customer> {
  await wait(150);
  return { ...find(id) };
}

export async function mockGetCustomerHistory(id: string): Promise<CustomerHistoryEntry[]> {
  await wait(150);
  return [...historyFor(find(id))].sort((a, b) => b.at - a.at);
}

export async function mockSetKyc(id: string, d: KycDecision): Promise<void> {
  await wait(500);
  const c = find(id), history = historyFor(c);
  if (c.kycStatus === d.status) return; // deciding what the customer already is changes nothing
  if (!kycMovesFrom(c.kycStatus).includes(d.status)) throw new ApiError(409, "invalid_transition", `A ${c.kycStatus} customer cannot be set to ${d.status}`);
  mockCustomers[indexOf(c)] = { ...c, kycStatus: d.status };
  history.push({ at: nowSec(), action: d.status === "verified" ? "KYC verified" : "KYC rejected", actor: "staff:1", reason: d.reason || "Identity checked" });
}
