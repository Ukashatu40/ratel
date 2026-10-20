import { useSearchParams } from "react-router";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { formatCount, formatWAT } from "../../lib/format";
import { getAudit } from "./api";

const PAGE_SIZE = 10;

// Every action taken across RatelDesk, newest first. Read-only: the audit trail is never edited.
export function AuditTab() {
  const [params, setParams] = useSearchParams();
  const q = params.get("q") ?? "";
  const page = Math.max(1, Number(params.get("page")) || 1);
  const { data, isPending, isError, refetch } = useQuery({ queryKey: ["audit", { q, page }], queryFn: () => getAudit({ q, page, pageSize: PAGE_SIZE }), placeholderData: keepPreviousData });

  const go = (next: { q?: string; page?: number }) => {
    const p = new URLSearchParams();
    p.set("tab", "audit");
    const nq = next.q ?? q, np = next.page ?? 1; // a new search goes back to page 1
    if (nq) p.set("q", nq);
    if (np > 1) p.set("page", String(np));
    setParams(p, { replace: true });
  };
  const total = data?.total ?? 0, last = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const from = total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1, to = Math.min(page * PAGE_SIZE, total);

  return (
    <div className="stf-col">
      <div className="card stf-search">
        <input value={q} onChange={(e) => go({ q: e.target.value })} placeholder="Search the audit log by staff, action or line" aria-label="Search the audit log" />
        {q && data && <span className="muted">{formatCount(total)} matches</span>}
      </div>
      <section className="card stf-card">
        {isError ? <div className="stf-message">Could not load the audit log. <button type="button" className="btn btn--sm" onClick={() => refetch()}>Try again</button></div> : (
          <table className="data-table">
            <thead><tr><th>Time (WAT)</th><th>Staff</th><th>Action</th><th>Target</th><th>Reason</th></tr></thead>
            <tbody>
              {isPending && <tr><td colSpan={5} className="muted">Loading...</td></tr>}
              {data?.items.map((e) => (
                <tr key={e.id}><td>{formatWAT(e.at)}</td><td>{e.actor}</td><td><b>{e.action}</b></td><td>{e.target}</td><td>{e.reason}</td></tr>
              ))}
              {data && data.items.length === 0 && <tr><td colSpan={5} className="muted">Nothing matches your search.</td></tr>}
            </tbody>
          </table>
        )}
        <div className="stf-footer">
          <span className="muted">Showing {from} to {to} of {formatCount(total)} entries</span>
          <div className="stf-pages">
            <button type="button" className="chip" disabled={page <= 1} onClick={() => go({ page: page - 1 })}>Previous</button>
            <span className="muted">Page {page} of {last}</span>
            <button type="button" className="chip" disabled={page >= last} onClick={() => go({ page: page + 1 })}>Next</button>
          </div>
        </div>
      </section>
    </div>
  );
}
