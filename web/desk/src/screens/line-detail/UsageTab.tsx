import { useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Badge } from "../../components/ui";
import { formatCount, formatDayWAT, formatMB, formatTimeWAT } from "../../lib/format";
import { getUsage } from "./api";

const PAGE_SIZE = 10;

// Usage records are 5-minute intervals read from the user plane (ogstun) by RatelMeter.
export function UsageTab({ imsi }: { imsi: string }) {
  const [page, setPage] = useState(1);
  const { data, isPending, isError, refetch } = useQuery({ queryKey: ["line", imsi, "usage", page], queryFn: () => getUsage(imsi, page, PAGE_SIZE), placeholderData: keepPreviousData });
  const total = data?.total ?? 0, last = Math.max(1, Math.ceil(total / PAGE_SIZE));
  return (
    <section className="card ld-table">
      <h3>Usage: 5-minute intervals</h3>
      {isError ? <div className="ld-message">Could not load usage. <button type="button" className="btn btn--sm" onClick={() => refetch()}>Try again</button></div> : (
        <table className="data-table">
          <thead><tr><th>Interval (WAT)</th><th>Uploaded (MB)</th><th>Downloaded (MB)</th><th>Rated</th><th>Source</th></tr></thead>
          <tbody>
            {isPending && <tr><td colSpan={5} className="muted">Loading...</td></tr>}
            {data?.items.map((r) => (
              <tr key={r.periodStart}>
                <td>{formatDayWAT(r.periodStart)}, {formatTimeWAT(r.periodStart)} to {formatTimeWAT(r.periodEnd)}</td>
                <td>{formatMB(r.bytesUp)}</td><td>{formatMB(r.bytesDown)}</td>
                <td>{r.rated ? <Badge tone="green">Rated</Badge> : <Badge tone="amber">Not yet</Badge>}</td>
                <td>{r.source}</td>
              </tr>
            ))}
            {data && data.items.length === 0 && <tr><td colSpan={5} className="muted">No usage yet.</td></tr>}
          </tbody>
        </table>
      )}
      <div className="ld-footer">
        <span className="muted">{formatCount(total)} intervals in the last 24 hours</span>
        <div className="ld-pages">
          <button type="button" className="chip" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</button>
          <span className="muted">Page {page} of {last}</span>
          <button type="button" className="chip" disabled={page >= last} onClick={() => setPage(page + 1)}>Next</button>
        </div>
      </div>
    </section>
  );
}