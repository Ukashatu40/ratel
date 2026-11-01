import { useQuery } from "@tanstack/react-query";
import { Badge } from "../../components/ui";
import { formatDuration, formatWAT } from "../../lib/format";
import { callsAvailable, getCalls } from "./api";

// Calls are free between Ratelplus lines for now, so there is no charge column.
export function CallsTab({ lineKey }: { lineKey: string }) {
  const available = callsAvailable();
  const { data, isPending, isError, refetch } = useQuery({ queryKey: ["line", lineKey, "calls"], queryFn: () => getCalls(lineKey), enabled: available });
  // TODO(contract): the call history waits for the call record agreement (#26); the API has no operation for it yet.
  if (!available) return <section className="card"><h3>Calls: VoLTE history</h3><p className="muted">Call history is not available yet. It starts once the call records from RatelVoice are agreed and stored.</p></section>;
  return (
    <section className="card ld-table">
      <h3>Calls: VoLTE history</h3>
      {isError ? <div className="ld-message">Could not load calls. <button type="button" className="btn btn--sm" onClick={() => refetch()}>Try again</button></div> : (
        <table className="data-table">
          <thead><tr><th>Start (WAT)</th><th>End (WAT)</th><th>Duration</th><th>Number</th><th>QCI 1 bearer</th><th>End reason</th></tr></thead>
          <tbody>
            {isPending && <tr><td colSpan={6} className="muted">Loading...</td></tr>}
            {data?.map((c) => (
              <tr key={c.callId}>
                <td>{formatWAT(c.startedAt)}</td>
                <td>{formatWAT(c.endedAt)}</td>
                <td>{formatDuration(c.answeredAt ? c.endedAt - c.answeredAt : 0)}</td>
                <td><span className="muted">{c.direction === "outgoing" ? "To" : "From"}</span> {c.number}</td>
                <td>{c.qci1Bearer === "established" ? <Badge tone="green">Established</Badge> : <Badge tone="grey">Not set up</Badge>}</td>
                <td>{c.endReason}</td>
              </tr>
            ))}
            {data && data.length === 0 && <tr><td colSpan={6} className="muted">No calls yet.</td></tr>}
          </tbody>
        </table>
      )}
    </section>
  );
}