import { Link, useSearchParams } from "react-router";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Badge, KycBadge } from "../../components/ui";
import { formatCount, initials, maskNin } from "../../lib/format";
import { getCustomers } from "./api";
import { CustomerDrawer } from "./CustomerDrawer";
import type { KycTab } from "./types";
import "./CustomersScreen.css";

const PAGE_SIZE = 10;
const TABS: { key: KycTab; label: string }[] = [
  { key: "all", label: "All" }, { key: "pending", label: "Pending" }, { key: "verified", label: "Verified" }, { key: "rejected", label: "Rejected" },
];
const isTab = (v: string | null): v is KycTab => TABS.some((t) => t.key === v);

export default function CustomersScreen() {
  // Search, KYC tab, page and the open customer all live in the URL: links can be shared and Back works.
  const [params, setParams] = useSearchParams();
  const q = params.get("q") ?? "";
  const tab: KycTab = isTab(params.get("kyc")) ? (params.get("kyc") as KycTab) : "all";
  const page = Math.max(1, Number(params.get("page")) || 1);
  const selected = params.get("customer");

  const { data, isPending, isError, refetch } = useQuery({
    queryKey: ["customers", { q, tab, page }],
    queryFn: () => getCustomers({ q, tab, page, pageSize: PAGE_SIZE }),
    placeholderData: keepPreviousData,
  });

  const go = (next: { q?: string; tab?: KycTab; page?: number }) => {
    const nq = next.q ?? q, nt = next.tab ?? tab, np = next.page ?? 1; // a new search or tab goes back to page 1
    const p = new URLSearchParams();
    if (nq) p.set("q", nq);
    if (nt !== "all") p.set("kyc", nt);
    if (np > 1) p.set("page", String(np));
    if (selected) p.set("customer", selected);
    setParams(p, { replace: true });
  };
  const open = (id: string | null) => {
    const p = new URLSearchParams(params);
    if (id) p.set("customer", id); else p.delete("customer");
    setParams(p, { replace: true });
  };

  const total = data?.total ?? 0, lastPage = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const from = total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1, to = Math.min(page * PAGE_SIZE, total);

  return (
    <div className={`cust${selected ? " cust--open" : ""}`}>
      <div>
        <h1>Customers</h1>
        <p className="muted" style={{ marginTop: 4 }}>Subscribers and their identity checks.</p>
      </div>

      <div className="card cust-search">
        <input className="cust-search__input" value={q} onChange={(e) => go({ q: e.target.value })} placeholder="Search by name, phone number or NIN" aria-label="Search customers" />
        {q && data && <span className="muted">{formatCount(data.counts.all)} matches</span>}
      </div>

      <div className="cust-tabs cust-tabs--main" role="tablist">
        {TABS.map((t) => (
          <button key={t.key} type="button" role="tab" aria-selected={tab === t.key} className={tab === t.key ? "on" : ""} onClick={() => go({ tab: t.key })}>
            {t.label}{data ? ` (${formatCount(data.counts[t.key])})` : ""}
          </button>
        ))}
      </div>

      <section className="card cust-card">
        {isError ? (
          <div className="cust-message">Could not load customers. <button type="button" className="btn btn--sm" onClick={() => refetch()}>Try again</button></div>
        ) : (
          <table className="data-table">
            <thead><tr><th>Customer</th><th>NIN</th><th>Phone</th><th>Email</th><th>Lines</th><th>KYC</th></tr></thead>
            <tbody>
              {isPending && <tr><td colSpan={6} className="muted">Loading...</td></tr>}
              {data?.items.map((c) => (
                <tr key={c.id} className={selected === c.id ? "cust-row--on" : ""} onClick={() => open(c.id)}>
                  <td>
                    <button type="button" className="cust-name" onClick={(e) => { e.stopPropagation(); open(c.id); }}>
                      <span className="avatar">{initials(c.name)}</span>{c.name}
                    </button>
                  </td>
                  <td>{maskNin(c.idNumber)}</td>
                  <td>{c.phone}</td>
                  <td>{c.email || <span className="muted">None</span>}</td>
                  <td>{c.linesCount > 0 ? <Link className="cust-link" to={`/lines?q=${encodeURIComponent(c.name)}`} onClick={(e) => e.stopPropagation()}>{c.linesCount}</Link> : 0}</td>
                  <td><div className="cust-tags"><KycBadge status={c.kycStatus} />{c.blocked && <Badge tone="red">Blocked</Badge>}</div></td>
                </tr>
              ))}
              {data && data.items.length === 0 && <tr><td colSpan={6} className="muted">No customers match your search.</td></tr>}
            </tbody>
          </table>
        )}
        <div className="cust-footer">
          <span className="muted">Showing {from} to {to} of {formatCount(total)} customers</span>
          <div className="cust-pages">
            <button type="button" className="chip" disabled={page <= 1} onClick={() => go({ page: page - 1 })}>Previous</button>
            <span className="muted">Page {page} of {lastPage}</span>
            <button type="button" className="chip" disabled={page >= lastPage} onClick={() => go({ page: page + 1 })}>Next</button>
          </div>
        </div>
      </section>

      {selected && <CustomerDrawer key={selected} id={selected} onClose={() => open(null)} />}
    </div>
  );
}
