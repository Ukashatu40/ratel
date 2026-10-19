import type { SimImportRow } from "./types";

export interface RowProblem { line: number; message: string }
export interface ParsedSims { rows: SimImportRow[]; problems: RowProblem[]; total: number; refused?: string }

const MAX_ROWS = 5000;
const clean = (s: string) => s.trim().replace(/^"|"$/g, "");

// Reads a SIM batch file. ONLY the three allowed columns are accepted. The header line is checked first,
// and if the file has anything else (for example a Ki or OPc column) the rest of the file is never read.
export async function readSimFile(file: File): Promise<ParsedSims> {
  const header = (await file.slice(0, 4096).text()).split(/\r?\n/)[0] ?? "";
  const cols = header.split(",").map((c) => clean(c).toLowerCase());
  const looksSecret = cols.some((c) => ["ki", "opc", "op", "key", "keys", "secret", "k4", "kic", "kid"].includes(c) || c.includes("opc") || c.includes("secret"));
  if (looksSecret) return { rows: [], problems: [], total: 0, refused: "This file has a SIM secret key column. Keys (Ki/OPc) go to RatelLink directly and must not be uploaded here. The file was not read." };
  const iccidAt = cols.indexOf("iccid"), imsiAt = cols.indexOf("imsi"), batchAt = cols.indexOf("batch");
  if (cols.length !== 3 || iccidAt < 0 || imsiAt < 0 || batchAt < 0) return { rows: [], problems: [], total: 0, refused: "The file must have exactly three columns: iccid, imsi and batch. The file was not read." };

  const lines = (await file.text()).split(/\r?\n/).slice(1).filter((l) => l.trim() !== "");
  if (lines.length > MAX_ROWS) return { rows: [], problems: [], total: lines.length, refused: `Too many rows (${lines.length}). Split the file into batches of at most ${MAX_ROWS}.` };

  const rows: SimImportRow[] = [], problems: RowProblem[] = [], seenIccid = new Set<string>(), seenImsi = new Set<string>();
  lines.forEach((l, i) => {
    const line = i + 2, parts = l.split(",").map(clean);
    const problem = (message: string) => problems.push({ line, message });
    if (parts.length !== 3) return problem("Wrong number of columns");
    const iccid = parts[iccidAt], imsi = parts[imsiAt], batch = parts[batchAt];
    if (!/^\d{18,20}$/.test(iccid)) return problem("ICCID must be 18 to 20 digits");
    if (!/^62100\d{10}$/.test(imsi)) return problem("IMSI must be 15 digits starting with 62100");
    if (!/^[\w-]{1,40}$/.test(batch)) return problem("Batch name is missing or has odd characters");
    if (seenIccid.has(iccid)) return problem("Repeated ICCID in this file");
    if (seenImsi.has(imsi)) return problem("Repeated IMSI in this file");
    seenIccid.add(iccid); seenImsi.add(imsi);
    rows.push({ iccid, imsi, batch });
  });
  return { rows, problems, total: lines.length };
}
