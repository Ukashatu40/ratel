import type { LineState } from "../dashboard/types";
import type { LineRow, LinesPage, LinesQuery, LineTab, SuspendPayload } from "./types";

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));
const NAMES = ["Fatima Bello", "Musa Ibrahim", "Yusuf Abdullahi", "Aisha Sani", "Zainab Lawal", "Hauwa Garba", "Sani Danjuma", "Bashir Aliyu", "Maryam Tijani", "Ibrahim Danladi", "Khadija Umar", "Abubakar Yahaya", "Halima Musa", "Garba Shehu", "Rabi Adamu", "Nura Salisu", "Amina Kabir", "Usman Idris", "Hadiza Lawan", "Kabiru Sule"];
const PLANS = ["Weekly 2GB", "Starter 5GB", "Family 20GB"];
const now = Math.floor(Date.now() / 1000);

const stateFor = (i: number): LineState =>
  i % 29 === 0 ? "awaiting_activation" : i % 23 === 0 ? "expired" : i % 17 === 0 ? "suspended" : i % 11 === 0 ? "out_of_data" : "active";

let lines: LineRow[] = Array.from({ length: 137 }, (_, i) => {
  const n = 100 + i, state = stateFor(i + 1);
  return {
    imsi: `621000000000${n}`, iccid: `89234000000000${10000 + n}`, msisdn: `+234 700 000 ${String(n).padStart(4, "0")}`,
    customerName: NAMES[i % NAMES.length], planName: PLANS[i % 3], state,
    planEndsEpoch: state === "awaiting_activation" ? null : now + (((i * 7) % 40) - 8) * 86400,
  };
});

export async function mockGetLines({ q, tab, page, pageSize }: LinesQuery): Promise<LinesPage> {
  await wait(200);
  const s = q.trim().toLowerCase(), digits = s.replace(/\s/g, "");
  const found = s ? lines.filter((l) => l.customerName.toLowerCase().includes(s) || l.msisdn.replace(/\s/g, "").includes(digits) || l.imsi.includes(digits) || l.iccid.includes(digits)) : lines;
  const count = (t: LineTab) => (t === "all" ? found.length : found.filter((l) => l.state === t).length);
  const shown = tab === "all" ? found : found.filter((l) => l.state === tab);
  return {
    items: shown.slice((page - 1) * pageSize, page * pageSize), total: shown.length,
    counts: { all: count("all"), active: count("active"), out_of_data: count("out_of_data"), suspended: count("suspended"), expired: count("expired") },
  };
}

export async function mockSuspend(imsi: string, _payload: SuspendPayload): Promise<void> {
  await wait(500);
  const line = lines.find((l) => l.imsi === imsi);
  if (!line || (line.state !== "active" && line.state !== "out_of_data")) throw new Error("Only active or out-of-data lines can be suspended");
  lines = lines.map((l) => (l.imsi === imsi ? { ...l, state: "suspended" } : l));
}

// Lets other mocks (like Line Detail) read the same lines, so a suspension shows up everywhere.
export const mockFindLine = (imsi: string): LineRow | undefined => lines.find((l) => l.imsi === imsi);
