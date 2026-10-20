import { useQuery } from "@tanstack/react-query";
import { formatCount, formatWAT } from "../../lib/format";
import { getSimBatches, getSimSummary } from "./api";
import { ImportPanel } from "./ImportPanel";

export function SimsTab() {
  const summary = useQuery({ queryKey: ["stock", "sims", "summary"], queryFn: getSimSummary });
  const batches = useQuery({ queryKey: ["stock", "sims", "batches"], queryFn: getSimBatches });
  const s = summary.data;
  return (
    <div className="stock-col">
      <div className="stock-counts">
        {([["In stock", s?.inStock], ["In use", s?.inUse], ["Retired", s?.retired]] as const).map(([label, n]) => (
          <div key={label} className="card"><div className="muted">{label}</div><div className="stock-count">{n === undefined ? "-" : formatCount(n)}</div></div>
        ))}
      </div>
      <div className="alert alert--warn"><b>SIM secret keys (Ki/OPc) are encrypted and transferred directly to RatelLink; they are never visible or stored in BSS/UI memory.</b></div>
      <ImportPanel />
      <section className="card stock-card">
        <h3>Recent SIM batches</h3>
        {batches.isError ? <div className="stock-message">Could not load batches. <button type="button" className="btn btn--sm" onClick={() => batches.refetch()}>Try again</button></div> : (
          <table className="data-table">
            <thead><tr><th>Batch</th><th>Imported (WAT)</th><th>SIMs</th><th>In stock</th><th>In use</th><th>Imported by</th></tr></thead>
            <tbody>
              {batches.isPending && <tr><td colSpan={6} className="muted">Loading...</td></tr>}
              {batches.data?.map((b) => (
                <tr key={b.batchId}><td><b>{b.batchId}</b></td><td>{formatWAT(b.importedAt)}</td><td>{formatCount(b.total)}</td><td>{formatCount(b.inStock)}</td><td>{formatCount(b.inUse)}</td><td>{b.importedBy}</td></tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
