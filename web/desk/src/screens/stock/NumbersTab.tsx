import { useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Badge, type Tone } from "../../components/ui";
import { formatCount, formatWAT } from "../../lib/format";
import { getNumbers } from "./api";
import type { NumberState, NumberTab } from "./types";

const PAGE_SIZE = 10;
const TABS: { key: NumberTab; label: string }[] = [{ key: "all", label: "All" }, { key: "available", label: "Available" }, { key: "in_use", label: "In use" }, { key: "quarantined", label: "Quarantined" }];
const TONE: Record<NumberState, Tone> = { available: "green", in_use: "blue", quarantined: "amber" };
const LABEL: Record<NumberState, string> = { available: "Available", in_use: "In use", quarantined: "Quarantined" };

export function NumbersTab() {
  const [q, setQ] = useState("");
  const [tab, setTab] = useState<NumberTab>("all");
  const [page, setPage] = useState(1);
  const { data, isPending, isError, refetch } = useQuery({ queryKey: ["stock", "numbers", { q, tab, page }], queryFn: () => getNumbers({ q, tab, page, pageSize: PAGE_SIZE }), placeholderData: keepPreviousData });
  const total = data?.total ?? 0, last = Math.max(1, Math.ceil(total / PAGE_SIZE));
  return (
    <div className="stock-col">
      <div className="card stock-search">
        <input value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} placeholder="Search a phone number" aria-label="Search numbers" />
      </div>
      <div className="stock-tabs" role="tablist">
        {TABS.map((t) => (
          <button key={t.key} type="button" role="tab" aria-selected={tab === t.key} className={tab === t.key ? "on" : ""} onClick={() => { setTab(t.key); setPage(1); }}>
            {t.label}{data ? ` (${formatCount(data.counts[t.key])})` : ""}
          </button>
        ))}
      </div>
      <section className="card stock-card">
        {isError ? <div className="stock-message">Could not load numbers. <button type="button" className="btn btn--sm" onClick={() => refetch()}>Try again</button></div> : (
          <table className="data-table">
            <thead><tr><th>Number</th><th>State</th><th>Available again from (WAT)</th></tr></thead>
            <tbody>
              {isPending && <tr><td colSpan={3} className="muted">Loading...</td></tr>}
              {data?.items.map((n) => (
                <tr key={n.msisdn}><td>{n.msisdn}</td><td><Badge tone={TONE[n.state]}>{LABEL[n.state]}</Badge></td><td>{n.availableFromEpoch ? formatWAT(n.availableFromEpoch) : <span className="muted">-</span>}</td></tr>
              ))}
              {data && data.items.length === 0 && <tr><td colSpan={3} className="muted">No numbers match.</td></tr>}
            </tbody>
          </table>
        )}
        <div className="stock-footer">
          <span className="muted">{formatCount(total)} numbers. Quarantined numbers wait for the period compliance sets.</span>
          <div className="stock-pages">
            <button type="button" className="chip" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</button>
            <span className="muted">Page {page} of {last}</span>
            <button type="button" className="chip" disabled={page >= last} onClick={() => setPage(page + 1)}>Next</button>
          </div>
        </div>
      </section>
    </div>
  );
}
