import { useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { newIdempotencyKey } from "../../lib/api";
import { importSims } from "./api";
import { readSimFile, type ParsedSims } from "./sim-csv";
import type { SimImportRow } from "./types";

const TEMPLATE = `data:text/csv;charset=utf-8,${encodeURIComponent("iccid,imsi,batch\n")}`;

// Batch import: the file may only contain ICCID, IMSI and batch. Anything else is refused before it is read.
export function ImportPanel() {
  const queryClient = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const [parsed, setParsed] = useState<(ParsedSims & { name: string }) | null>(null);
  const [reading, setReading] = useState(false);
  const [done, setDone] = useState<number | null>(null);
  const [key, setKey] = useState(newIdempotencyKey); // one key per file, so a retry cannot import it twice

  const imp = useMutation({
    mutationFn: (rows: SimImportRow[]) => importSims(rows, key),
    onSuccess: (r) => {
      setDone(r.imported);
      setParsed(null);
      void queryClient.invalidateQueries({ queryKey: ["stock"] });
    },
  });

  const choose = async (file: File | undefined) => {
    if (!file) return;
    setReading(true); setDone(null); imp.reset();
    setParsed({ name: file.name, ...(await readSimFile(file)) });
    setKey(newIdempotencyKey());
    setReading(false);
    if (input.current) input.current.value = ""; // so the same file can be picked again
  };

  return (
    <section className="card">
      <div className="stock-split"><h3>Import a SIM batch</h3><a className="stock-link" href={TEMPLATE} download="sim-batch-template.csv">Download the template</a></div>
      <label className="stock-drop" onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); void choose(e.dataTransfer.files[0]); }}>
        <input ref={input} type="file" accept=".csv,text/csv" onChange={(e) => void choose(e.target.files?.[0])} />
        <b>{reading ? "Checking the file..." : "Drop the SIM batch file here, or click to choose it"}</b>
        <span className="muted">CSV with the columns iccid, imsi, batch</span>
      </label>

      {parsed?.refused && <div className="alert alert--danger" role="alert" style={{ marginTop: 14 }}><b>{parsed.name}:</b> {parsed.refused}</div>}

      {parsed && !parsed.refused && (
        <div style={{ marginTop: 14 }}>
          <p><b>{parsed.name}</b>: {parsed.rows.length} SIMs ready{parsed.problems.length > 0 && `, ${parsed.problems.length} rows with problems`}.</p>
          {parsed.problems.length > 0 && (
            <>
              <ul className="stock-problems">
                {parsed.problems.slice(0, 5).map((p) => <li key={p.line}>Line {p.line}: {p.message}</li>)}
                {parsed.problems.length > 5 && <li>... and {parsed.problems.length - 5} more</li>}
              </ul>
              <p className="muted">Fix the file and choose it again. Nothing is imported until every row is valid.</p>
            </>
          )}
          {imp.isError && <div className="alert alert--danger" style={{ margin: "10px 0" }}>{imp.error.message}</div>}
          <button type="button" className="btn" style={{ marginTop: 10 }} disabled={parsed.problems.length > 0 || parsed.rows.length === 0 || imp.isPending} onClick={() => imp.mutate(parsed.rows)}>
            {imp.isPending ? "Importing..." : `Import ${parsed.rows.length} SIMs`}
          </button>
        </div>
      )}
      {done !== null && <div className="alert alert--warn" style={{ marginTop: 14 }}>Imported {done} SIMs. They now appear in stock.</div>}
    </section>
  );
}
