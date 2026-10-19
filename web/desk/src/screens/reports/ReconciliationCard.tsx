import { Link } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { Badge } from "../../components/ui";
import { RingChart } from "../../components/charts/charts";
import { formatCount, formatDateShort, formatNaira, formatWAT } from "../../lib/format";
import { getReconciliation } from "./api";

// The nightly check: every wallet balance must equal the sum of its ledger entries. Shows the latest run.
export function ReconciliationCard() {
  const { data, isPending, isError, refetch } = useQuery({ queryKey: ["reports", "reconciliation"], queryFn: getReconciliation, refetchInterval: 60_000 });
  if (isPending) return <div className="card skeleton" style={{ height: 260 }} aria-busy="true" />;
  if (isError) return <div className="card rep-message">Could not load the reconciliation. <button type="button" className="btn btn--sm" onClick={() => refetch()}>Try again</button></div>;

  const bad = data.mismatches.length;
  const ok = data.status === "ok";
  const fraction = data.walletsChecked ? data.matching / data.walletsChecked : 1;
  const badge = data.status === "running" ? <Badge tone="blue">Running now</Badge> : data.status === "failed" ? <Badge tone="red">Last run failed</Badge> : ok ? <Badge tone="green">All balances match</Badge> : <Badge tone="red">{bad} {bad === 1 ? "wallet does" : "wallets do"} not match</Badge>;
  return (
    <section className="card">
      <h3>Nightly reconciliation</h3>
      <div className="rep-recon">
        <RingChart fraction={fraction} label={`${Math.floor(fraction * 100)}%`} sub="match" color={ok ? "#008751" : "#e4002b"} size={130} thickness={14} />
        <div className="rep-recon__facts">
          <div style={{ marginBottom: 8 }}>{badge}</div>
          <div className="rep-kv"><span>Last run</span><span>{formatWAT(data.ranAt)}</span></div>
          <div className="rep-kv"><span>Wallets checked</span><span>{formatCount(data.walletsChecked)}</span></div>
          <div className="rep-kv"><span>Match their ledger</span><span>{formatCount(data.matching)}</span></div>
          <div className="rep-kv"><span>Mismatches</span><b className={bad ? "rep-bad" : ""}>{formatCount(bad)}</b></div>
        </div>
      </div>
      <div className="rep-runs" aria-label="Last 7 nights">
        {data.recentRuns.map((r) => (
          <span key={r.date} title={`${formatDateShort(r.date)}: ${r.mismatchCount === 0 ? "all match" : `${r.mismatchCount} mismatches`}`} className={`rep-runs__dot${r.mismatchCount ? " rep-runs__dot--bad" : ""}`} />
        ))}
        <span className="muted">last 7 nights</span>
      </div>
      <p className="muted rep-note">Compares every wallet balance with the sum of its ledger entries. Any mismatch raises an alert.</p>

      {bad > 0 && (
        <table className="data-table rep-mismatch">
          <thead><tr><th>Line</th><th>Wallet</th><th>Ledger sum</th><th>Difference</th></tr></thead>
          <tbody>
            {data.mismatches.map((m) => (
              <tr key={m.imsi}>
                <td><Link className="rep-link" to={`/finance/wallet?line=${m.imsi}`} title={m.msisdn}>{m.lineId}</Link></td>
                <td>{formatNaira(m.walletKobo)}</td><td>{formatNaira(m.ledgerSumKobo)}</td>
                <td className="rep-bad">{formatNaira(m.walletKobo - m.ledgerSumKobo)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
