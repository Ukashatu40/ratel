import { ApiError } from "../../lib/api";
import type { LineState } from "../dashboard/types";
import type { CareKind, CarePayload, LineRow, LinesPage, LinesQuery, LineTab } from "./types";

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));
const NAMES = ["Fatima Bello", "Musa Ibrahim", "Yusuf Abdullahi", "Aisha Sani", "Zainab Lawal", "Hauwa Garba", "Sani Danjuma", "Bashir Aliyu", "Maryam Tijani", "Ibrahim Danladi", "Khadija Umar", "Abubakar Yahaya", "Halima Musa", "Garba Shehu", "Rabi Adamu", "Nura Salisu", "Amina Kabir", "Usman Idris", "Hadiza Lawan", "Kabiru Sule"];
export const MOCK_PLAN_NAMES = ["Weekly 2GB", "Starter 5GB", "Family 20GB"]; // plan ids "1", "2", "3"
const now = Math.floor(Date.now() / 1000);

const stateFor = (i: number): LineState =>
  i % 29 === 0 ? "awaiting_activation" : i % 23 === 0 ? "expired" : i % 17 === 0 ? "suspended" : i % 11 === 0 ? "out_of_data" : "active";

let lines: LineRow[] = Array.from({ length: 137 }, (_, i) => {
  const n = 100 + i, state = stateFor(i + 1);
  return {
    lineId: n, planId: String((i % 3) + 1),
    imsi: `621000000000${n}`, iccid: `89234000000000${10000 + n}`, msisdn: `234700000${String(n).padStart(4, "0")}`, // the stored form
    customerName: NAMES[i % NAMES.length], planName: MOCK_PLAN_NAMES[i % 3], state,
    planEndsEpoch: state === "awaiting_activation" ? null : now + (((i * 7) % 40) - 8) * 86400,
  };
});
const before = new Map<number, LineState>(); // the state a suspended line had, for reinstate

export async function mockGetLines({ q, tab, page, pageSize }: LinesQuery): Promise<LinesPage> {
  await wait(200);
  const s = q.trim().toLowerCase(), digits = s.replace(/\D/g, "");
  const found = s ? lines.filter((l) => l.customerName.toLowerCase().includes(s) || (digits !== "" && (l.msisdn.includes(digits) || l.imsi.includes(digits) || l.iccid.includes(digits)))) : lines;
  const count = (t: LineTab) => (t === "all" ? found.length : found.filter((l) => l.state === t).length);
  const shown = tab === "all" ? found : found.filter((l) => l.state === tab);
  return {
    items: shown.slice((page - 1) * pageSize, page * pageSize).map((l) => ({ ...l })), total: shown.length,
    counts: {
      all: count("all"), awaiting_activation: count("awaiting_activation"), active: count("active"), out_of_data: count("out_of_data"),
      expired: count("expired"), suspended: count("suspended"), terminated: count("terminated"),
    },
  };
}

// The same transitions as the line state machine: suspend from active or out_of_data, reinstate from suspended,
// terminate from anything but terminated.
export async function mockCareAction(kind: CareKind, lineId: number, _payload: CarePayload): Promise<void> {
  await wait(500);
  const line = lines.find((l) => l.lineId === lineId);
  if (!line) throw new ApiError(404, "line_not_found", "No such line");
  const invalid = new ApiError(409, "invalid_transition", `A line that is ${line.state.replace("_", " ")} cannot be ${kind === "terminate" ? "terminated" : kind + "ed"}`);
  let next: LineState;
  if (kind === "suspend") {
    if (line.state !== "active" && line.state !== "out_of_data") throw invalid;
    before.set(lineId, line.state);
    next = "suspended";
  } else if (kind === "reinstate") {
    if (line.state !== "suspended") throw invalid;
    next = before.get(lineId) ?? "active";
  } else {
    if (line.state === "terminated") throw invalid;
    next = "terminated";
  }
  lines = lines.map((l) => (l.lineId === lineId ? { ...l, state: next } : l));
}

// Lets other mocks read the same lines, so a change shows up everywhere. The key is a line id or an IMSI.
export const mockFindLine = (key: string | number): LineRow | undefined =>
  lines.find((l) => String(l.lineId) === String(key) || l.imsi === String(key));

// For the sale: a line created by the sell journey, and its later states.
export const mockNextLineId = (): number => Math.max(...lines.map((l) => l.lineId)) + 1;
export const mockAddLine = (line: LineRow): void => { lines = [line, ...lines]; };
export const mockSetLineState = (lineId: number, state: LineState, planEndsEpoch: number | null): void => {
  lines = lines.map((l) => (l.lineId === lineId ? { ...l, state, planEndsEpoch } : l));
};
