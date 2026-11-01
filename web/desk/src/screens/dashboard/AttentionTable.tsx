import { useState } from "react";
import { Link } from "react-router";
import { Badge, StateBadge } from "../../components/ui";
import { formatMsisdn, formatWAT, initials } from "../../lib/format";
import type { AttentionItem } from "./types";

type Filter = "all" | "out_of_data" | "pending_kyc";
const FILTERS: { key: Filter; label: string }[] = [
  { key: "all", label: "All" },
  { key: "out_of_data", label: "Out of data" },
  { key: "pending_kyc", label: "Pending KYC" },
];

export function AttentionTable({ items }: { items: AttentionItem[] }) {
  const [filter, setFilter] = useState<Filter>("all");
  const rows = filter === "all" ? items : items.filter((i) => i.issue === filter);
  return (
    <section className="card attention">
      <div className="attention__head">
        <h3>Lines requiring immediate attention</h3>
        {FILTERS.map((f) => (
          <button key={f.key} className={`chip${filter === f.key ? " chip--on" : ""}`} onClick={() => setFilter(f.key)}>{f.label}</button>
        ))}
      </div>
      <table className="data-table">
        <thead>
          <tr><th>Customer</th><th>Phone number</th><th>Issue</th><th>Since (WAT)</th><th>Actions</th></tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={`${r.issue}-${r.customerId}-${r.lineId ?? 0}`}>
              <td><div className="attention__name"><span className="avatar">{initials(r.customerName)}</span>{r.customerName}</div></td>
              <td>{r.msisdn ? formatMsisdn(r.msisdn) : <span className="muted">No line yet</span>}</td>
              <td>{r.issue === "pending_kyc" ? <Badge tone="amber">Pending KYC</Badge> : <StateBadge state="out_of_data" />}</td>
              <td>{formatWAT(r.sinceEpoch)}</td>
              <td>
                <div className="attention__actions">
                  {r.issue === "pending_kyc" ? (
                    <Link className="btn btn--outline btn--sm" to={`/customers?customer=${r.customerId}`}>Review KYC</Link>
                  ) : r.lineId !== null ? (
                    <Link className="btn btn--outline btn--sm" to={`/lines/${r.lineId}`}>View</Link>
                  ) : null}
                </div>
              </td>
            </tr>
          ))}
          {rows.length === 0 && <tr><td colSpan={5} className="muted">Nothing needs attention here.</td></tr>}
        </tbody>
      </table>
    </section>
  );
}