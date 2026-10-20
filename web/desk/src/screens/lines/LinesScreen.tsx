import { useState } from "react";
import { Link, useSearchParams } from "react-router";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { StateBadge } from "../../components/ui";
import { formatCount, formatWAT, initials } from "../../lib/format";
import { getLines } from "./api";
import { RowMenu } from "./RowMenu";
import { SuspendDialog } from "./SuspendDialog";
import type { LineRow, LineTab } from "./types";
import "./LinesScreen.css";

const PAGE_SIZE = 10;
const TABS: { key: LineTab; label: string }[] = [
  { key: "all", label: "All" }, { key: "active", label: "Active" }, { key: "out_of_data", label: "Out of Data" },
  { key: "suspended", label: "Suspended" }, { key: "expired", label: "Expired" },
];
const isTab = (v: string | null): v is LineTab => TABS.some((t) => t.key === v);

// 1 2 3 ... 12  (current page and its neighbours, plus first and last)
function pageWindow(current: number, last: number): (number | "…")[] {
  const keep = new Set([1, last, current - 1, current, current + 1].filter((n) => n >= 1 && n <= last));
  const out: (number | "…")[] = [];
  [...keep].sort((a, b) => a - b).forEach((n, i, all) => { if (i > 0 && n - all[i - 1] > 1) out.push("…"); out.push(n); });
  return out;
}

export default function LinesScreen() {
  // The search, state tab and page live in the URL, so a filtered view can be bookmarked and Back works.
  const [params, setParams] = useSearchParams();
  const q = params.get("q") ?? "";
  const tab: LineTab = isTab(params.get("state")) ? (params.get("state") as LineTab) : "all";
  const page = Math.max(1, Number(params.get("page")) || 1);
  const [suspending, setSuspending] = useState<LineRow | null>(null);

  const { data, isPending, isError, refetch } = useQuery({
    queryKey: ["lines", { q, tab, page }],
    queryFn: () => getLines({ q, tab, page, pageSize: PAGE_SIZE }),
    placeholderData: keepPreviousData, // keep the old rows on screen while the new ones load
  });

  const go = (next: { q?: string; tab?: LineTab; page?: number }) => {
    const nq = next.q ?? q, nt = next.tab ?? tab, np = next.page ?? 1; // changing the search or tab goes back to page 1
    const p = new URLSearchParams();
    if (nq) p.set("q", nq);
    if (nt !== "all") p.set("state", nt);
    if (np > 1) p.set("page", String(np));
    setParams(p, { replace: true });
  };

  const total = data?.total ?? 0;
  const lastPage = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const from = total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;
  const to = Math.min(page * PAGE_SIZE, total);

  return (
    <div className="lines">
      <div className="lines__title">
        <div>
          <h1>Lines</h1>
          <p className="muted">Search by phone number, ICCID or IMSI. Results filter as you type.</p>
        </div>
        <Link to="/sales/activate" className="btn">Sell SIM</Link>
      </div>

      <div className="card lines__search">
        <input className="lines__input" value={q} onChange={(e) => go({ q: e.target.value })} placeholder="Search by name, phone number, ICCID or IMSI" aria-label="Search lines" autoFocus />
        {q && data && <span className="muted">{formatCount(data.counts.all)} matches</span>}
      </div>

      <div className="lines__tabs" role="tablist">
        {TABS.map((t) => (
          <button key={t.key} type="button" role="tab" aria-selected={tab === t.key} className={tab === t.key ? "on" : ""} onClick={() => go({ tab: t.key })}>
            {t.label}{data ? ` (${formatCount(data.counts[t.key])})` : ""}
          </button>
        ))}
      </div>

      <section className="card lines__card">
        {isError ? (
          <div className="lines__message">Could not load lines. <button type="button" className="btn btn--sm" onClick={() => refetch()}>Try again</button></div>
        ) : (
          <table className="data-table">
            <thead>
              <tr><th>Customer</th><th>Phone number</th><th>IMSI</th><th>ICCID</th><th>Plan</th><th>State</th><th>Plan ends (WAT)</th><th>Actions</th></tr>
            </thead>
            <tbody>
              {isPending && <tr><td colSpan={8} className="muted">Loading...</td></tr>}
              {data?.items.map((l) => (
                <tr key={l.imsi}>
                  <td><div className="lines__name"><span className="avatar">{initials(l.customerName)}</span>{l.customerName}</div></td>
                  <td><Link className="lines__link" to={`/lines/${l.imsi}`}>{l.msisdn}</Link></td>
                  <td>{l.imsi}</td>
                  <td>{l.iccid}</td>
                  <td>{l.planName}</td>
                  <td><StateBadge state={l.state} /></td>
                  <td>{l.planEndsEpoch ? formatWAT(l.planEndsEpoch) : "Not started"}</td>
                  <td><RowMenu line={l} onSuspend={setSuspending} /></td>
                </tr>
              ))}
              {data && data.items.length === 0 && <tr><td colSpan={8} className="muted">No lines match your search.</td></tr>}
            </tbody>
          </table>
        )}
        <div className="lines__footer">
          <span className="muted">Showing {from} to {to} of {formatCount(total)} lines</span>
          <div className="lines__pages">
            <button type="button" className="chip" disabled={page <= 1} onClick={() => go({ page: page - 1 })}>Previous</button>
            {pageWindow(page, lastPage).map((n, i) => n === "…" ? <span key={`gap${i}`} className="muted">…</span> : (
              <button key={n} type="button" className={`chip${n === page ? " chip--on" : ""}`} onClick={() => go({ page: n })} aria-current={n === page ? "page" : undefined}>{n}</button>
            ))}
            <button type="button" className="chip" disabled={page >= lastPage} onClick={() => go({ page: page + 1 })}>Next</button>
          </div>
        </div>
      </section>

      {suspending && <SuspendDialog key={suspending.imsi} line={suspending} onClose={() => setSuspending(null)} />}
    </div>
  );
}