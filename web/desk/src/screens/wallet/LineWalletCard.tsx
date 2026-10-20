import { Link } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { Badge } from "../../components/ui";
import { formatNaira, initials } from "../../lib/format";
import { getLineWallet } from "./api";

export function LineWalletCard({ imsi, onClear }: { imsi: string; onClear: () => void }) {
  const { data, isPending, isError, refetch } = useQuery({ queryKey: ["wallet", "line", imsi], queryFn: () => getLineWallet(imsi) });
  if (isPending) return <div className="card skeleton" style={{ height: 120 }} aria-busy="true" />;
  if (isError) return <div className="card wal-message">Could not load this wallet. <button type="button" className="btn btn--sm" onClick={() => refetch()}>Try again</button> <button type="button" className="btn btn--outline btn--sm" onClick={onClear}>Show all lines</button></div>;
  const matches = data.balanceKobo === data.ledgerSumKobo; // a wallet's balance must always equal the sum of its ledger entries
  return (
    <section className="card wal-line">
      <span className="avatar wal-line__avatar">{initials(data.customerName)}</span>
      <div className="wal-line__who">
        <div className="muted">Wallet of</div>
        <b>{data.msisdn}</b>
        <div className="muted">{data.customerName}</div>
      </div>
      <div className="wal-line__balance">
        <div className="muted">Balance</div>
        <div className="wal-line__amount">{formatNaira(data.balanceKobo)}</div>
        {matches ? <Badge tone="green">Matches the ledger</Badge> : <Badge tone="red">Does not match the ledger</Badge>}
      </div>
      <div className="wal-line__actions">
        <Link className="btn btn--outline btn--sm" to={`/lines/${imsi}`}>View line</Link>
        <button type="button" className="btn btn--outline btn--sm" onClick={onClear}>Show all lines</button>
      </div>
      <p className="muted wal-line__note">Customers top up on RatelPay with a voucher or a card. Staff top-ups are not available yet.</p>
    </section>
  );
}
