import { useState } from "react";
import { Link } from "react-router";
import { Badge, StateBadge } from "../../components/ui";
import { formatWAT, initials } from "../../lib/format";
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
          <tr><th>Customer</th><th>Phone number</th><th>Issue</th><th>Plan</th><th>Since (WAT)</th><th>Actions</th></tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.imsi}>
              <td><div className="attention__name"><span className="avatar">{initials(r.customerName)}</span>{r.customerName}</div></td>
              <td>{r.msisdn}</td>
              <td>{r.issue === "pending_kyc" ? <Badge tone="amber">Pending KYC</Badge> : <StateBadge state="out_of_data" />}</td>
              <td>{r.planName}</td>
              <td>{formatWAT(r.sinceEpoch)}</td>
              <td>
                <div className="attention__actions">
                  {r.issue === "pending_kyc" ? (
                    <Link className="btn btn--outline btn--sm" to="/customers">Review KYC</Link>
                  ) : (
                    <>
                      <Link className="btn btn--outline btn--sm" to={`/lines/${r.imsi}`}>View</Link>
                      <Link className="btn btn--outline btn--sm" to={`/lines/${r.imsi}?action=topup`}>Top-up</Link>
                    </>
                  )}
                </div>
              </td>
            </tr>
          ))}
          {rows.length === 0 && <tr><td colSpan={6} className="muted">Nothing needs attention here.</td></tr>}
        </tbody>
      </table>
    </section>
  );
}