import { useQuery } from "@tanstack/react-query";
import { formatWAT } from "../../lib/format";
import { getStockHistory } from "./api";

// The audit trail for stock (ACC-3): imports, voucher batch steps and card locks, newest first.
export function StockHistoryTab() {
  const { data, isPending, isError, refetch } = useQuery({ queryKey: ["stock", "history"], queryFn: getStockHistory });
  return (
    <section className="card">
      <h3>History</h3>
      {isPending && <p className="muted">Loading...</p>}
      {isError && <div className="stock-message">Could not load the history. <button type="button" className="btn btn--sm" onClick={() => refetch()}>Try again</button></div>}
      <ol className="stock-timeline">
        {data?.map((e) => (
          <li key={`${e.at}-${e.action}-${e.detail}`}><b>{e.action}</b> by {e.actor}<small>{formatWAT(e.at)}{e.detail ? ` | ${e.detail}` : ""}</small></li>
        ))}
      </ol>
    </section>
  );
}
