import { useQuery } from "@tanstack/react-query";
import { formatWAT } from "../../lib/format";
import { getHistory } from "./api";

// The audit trail (ACC-3): append-only, newest first. Every change shows who made it and why.
export function HistoryTab({ imsi }: { imsi: string }) {
  const { data, isPending, isError, refetch } = useQuery({ queryKey: ["line", imsi, "history"], queryFn: () => getHistory(imsi) });
  return (
    <section className="card">
      <h3>History</h3>
      {isPending && <p className="muted">Loading...</p>}
      {isError && <div className="ld-message">Could not load the history. <button type="button" className="btn btn--sm" onClick={() => refetch()}>Try again</button></div>}
      <ol className="ld-timeline">
        {data?.map((e) => (
          <li key={`${e.at}-${e.to}`}>
            <b>{e.from ? `${e.from} to ${e.to}` : e.to}</b> by {e.actor}
            <small>{formatWAT(e.at)} &nbsp;|&nbsp; {e.reason}</small>
          </li>
        ))}
      </ol>
      {data && data.length === 0 && <p className="muted">No changes recorded yet.</p>}
    </section>
  );
}