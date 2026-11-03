import { useInfiniteQuery } from "@tanstack/react-query";
import { Badge } from "../../components/ui";
import { formatCount, formatDuration, formatMsisdn, formatWAT } from "../../lib/format";
import { getCalls } from "./api";
import type { EndReason } from "./types";

// How a call ended, in words for staff. The set is the agreement's proposal (types.ts); the tones follow what
// the caller or the customer would call a good outcome.
const RESULT: Record<EndReason, { label: string; tone: "green" | "grey" | "amber" | "red" }> = {
  completed: { label: "Answered", tone: "green" },
  cancelled: { label: "Caller hung up before it was answered", tone: "grey" },
  declined: { label: "Declined", tone: "grey" },
  not_answered: { label: "Not answered (busy or no reply)", tone: "amber" },
  unavailable: { label: "Could not be reached", tone: "amber" },
  failed: { label: "Failed", tone: "red" },
};

// Calls are free between Ratelplus lines for now, so there is no charge column.
export function CallsTab({ lineKey, msisdn }: { lineKey: string; msisdn: string }) {
  const { data, isPending, isError, refetch, hasNextPage, fetchNextPage, isFetchingNextPage } = useInfiniteQuery({
    queryKey: ["line", lineKey, "calls"],
    queryFn: ({ pageParam }) => getCalls(lineKey, msisdn, pageParam),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.nextCursor,
  });
  const items = data?.pages.flatMap((p) => p.items) ?? [];
  return (
    <section className="card ld-table">
      <h3>Calls: VoLTE history</h3>
      {isError ? <div className="ld-message">Could not load calls. <button type="button" className="btn btn--sm" onClick={() => refetch()}>Try again</button></div> : (
        <table className="data-table">
          <thead><tr><th>Start (WAT)</th><th>Number</th><th>Rang for</th><th>Talk time</th><th>Result</th></tr></thead>
          <tbody>
            {isPending && <tr><td colSpan={5} className="muted">Loading...</td></tr>}
            {items.map((c) => {
              const result = RESULT[c.endReason] ?? { label: c.endReason, tone: "grey" as const };
              return (
                <tr key={c.callId}>
                  <td>{formatWAT(c.startedAt)}</td>
                  <td><span className="muted">{c.direction === "outgoing" ? "To" : "From"}</span> {formatMsisdn(c.number)}</td>
                  <td>{formatDuration((c.answeredAt ?? c.endedAt) - c.startedAt)}</td>
                  <td>{c.answeredAt ? formatDuration(c.endedAt - c.answeredAt) : <span className="muted">none</span>}</td>
                  <td><Badge tone={result.tone}>{result.label}</Badge></td>
                </tr>
              );
            })}
            {data && items.length === 0 && <tr><td colSpan={5} className="muted">No calls in the last 30 days.</td></tr>}
          </tbody>
        </table>
      )}
      <div className="ld-footer">
        <span className="muted">{formatCount(items.length)} calls shown, from the last 30 days</span>
        {hasNextPage && (
          <button type="button" className="chip" onClick={() => void fetchNextPage()} disabled={isFetchingNextPage}>{isFetchingNextPage ? "Loading..." : "Show older"}</button>
        )}
      </div>
    </section>
  );
}
